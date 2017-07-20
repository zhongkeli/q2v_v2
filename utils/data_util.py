# coding=utf-8
"""util for data processing"""
import os
import sys
import re
import codecs
import string
import random
from nltk import word_tokenize
from nltk.stem import WordNetLemmatizer
from utils.pickle_util import save_obj_pickle
from utils.cache_util import RandomSet
from enum import Enum, unique
from collections import Counter
import numpy as np
from itertools import chain
from config.config import end_token
from itertools import combinations

wn_lemmatizer = WordNetLemmatizer()

_WORD_SPLIT = re.compile(b"([.,!?\"';-@#)(])".decode())
_DIGIT_RE = re.compile(br"\d".decode())


@unique
class aksis_data_label(Enum):
    negative_label = 0
    positive_label = 1


def sentence_gen(files):
    """Generator that yield each sentence in a line.
    Parameters
    ----------
        files: list
            data file list
    """
    if not isinstance(files, list):
        files = [files]
    for filename in files:
        with codecs.open(filename, encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip().lower()
                if len(line):
                    yield line


def aksis_sentence_gen(filename):
    """Generator that yield each sentence in aksis corpus.
    Parameters
    ----------
        filename: str
            data file name
    """
    for line in sentence_gen(filename):
        line = extract_query_title_from_aksis_data(line)
        if len(line):
            yield line


def stem_tokens(tokens, lemmatizer):
    """lemmatizer
    Parameters
    ----------
        tokens: list
            token for lemmatizer
        lemmatizer: stemming model
            default model is wordnet lemmatizer
    """
    return [lemmatizer.lemmatize(token) for token in tokens]


def tokenize(text, lemmatizer=wn_lemmatizer):
    """tokenize and lemmatize the text"""
    text = clean_html(text)
    tokens = word_tokenize(text)
    tokens = [i for i in tokens if i not in string.punctuation]
    stems = stem_tokens(tokens, lemmatizer)
    return stems


def extract_query_title_from_aksis_data(sentence):
    """extract the query and title from aksis raw data, this function is for building up vocabulary
    Aksis data format: MarketplaceId\tAsin\tKeyword\t Score\tActionType\tDate
    ActioType: 1-KeywordsByAdds, 2-KeywordsBySearches, 3-KeywordsByPurchases, 4-KeywordsByClicks
    """
    sentence = sentence.strip().lower()
    items = re.split(r'\t+', sentence)
    if len(items) == 7 and len(items[2]) and len(items[6]):
        return items[2] + " " + items[6]
    else:
        return str()


def extract_raw_query_title_score_from_aksis_data(sentence):
    """extract the query, title and score from aksis raw data, this function is to generate training data
    score gives a rough idea about specificness of a query. For example query1: "iphone" and query2: "iphone 6s 64GB".
    In both the query customer is looking for iphone but query2 is more specific.
    Query specificity score is number which ranges from 0.0 to 1.0.
    Aksis data format: MarketplaceId\tAsin\tKeyword\t Score\tActionType\tDate
    ActioType: 1-KeywordsByAdds, 2-KeywordsBySearches, 3-KeywordsByPurchases, 4-KeywordsByClicks
    """
    sentence = sentence.strip().lower()
    items = re.split(r'\t+', sentence)
    if len(items) == 7 and len(items[2]) and len(items[3]) and len(items[6]):
        return items[2], items[6], items[3]
    else:
        return None, None, None


def query_title_score_generator_from_aksis_data(files, dropout=-1):
    """Generator that yield query, title, score in aksis corpus"""
    for line in sentence_gen(files):
        query, title, score = extract_raw_query_title_score_from_aksis_data(line)
        if query and title and score:
            if not is_hit(score, dropout):
                continue
            yield query, title


def query_pair_generator_from_aksis_data(files, nouse=-1):
    for sentence in sentence_gen(files):
        sentence = sentence.strip().lower()
        sentence = re.sub(r'(?:^\(|\)$)', '', sentence)
        items = re.split(r'\t+', sentence)
        if len(items) > 2:
            items = items[1:]
        yield items


def negative_sampling_query_pair_data_generator(files, neg_number, dropout=-1):
    capacity = 65536
    rs = RandomSet(capacity)
    query_pair_set = RandomSet(capacity)
    for items in query_pair_generator_from_aksis_data(files, dropout):
        current_query_pair_set = set()
        for item in combinations(items, 2):
            if len(item[0].split()) < 2 or len(item[1].split()) < 2:
                continue
            current_query_pair_set.add(item[0])
            current_query_pair_set.add(item[1])
            if len(rs) > capacity - 100:
                query_pair_set.add((item[0], item[1], aksis_data_label.positive_label.value))
                for neg_query in rs.get_n_items(neg_number):
                    query = random.choice(item)
                    if query != neg_query:
                        query_pair_set.add((query, neg_query, aksis_data_label.negative_label.value))
        # rs.update(current_query_pair_set)
        if len(current_query_pair_set) > 1:
            rs.add(random.sample(current_query_pair_set, 1)[0])

        for _ in range(5):
            ele = query_pair_set.pop()
            if ele:
                yield ele
            else:
                break


def negative_sampling_train_data_generator(files, neg_number, dropout=-1):
    rs = RandomSet()
    for query, title in query_title_score_generator_from_aksis_data(files, dropout):
        rs.add(title)
        yield query, title, aksis_data_label.positive_label.value
        for neg_title in rs.get_n_items(neg_number):
            yield query, neg_title, aksis_data_label.negative_label.value


def is_hit(score, dropout):
    """sample function to decide whether the data should be trained,
    not sample if dropout less than 0"""
    return dropout < 0 or float(score) > random.uniform(dropout, 1)


def clean_html(html):
    """
    Copied from NLTK package.
    Remove HTML markup from the given string.

    Parameters
    ----------
        html: str
            the HTML string to be cleaned
    """

    # First we remove inline JavaScript/CSS:
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", "", html.strip())
    # Then we remove html comments. This has to be done before removing regular
    # tags since comments can contain '>' characters.
    cleaned = re.sub(r"(?s)<!--(.*?)-->[\n]?", "", cleaned)
    # Next we can remove the remaining tags:
    cleaned = re.sub(r"(?s)<.*?>", " ", cleaned)
    # Finally, we deal with whitespace
    cleaned = re.sub(r"&nbsp;", " ", cleaned)
    cleaned = re.sub(r"  ", " ", cleaned)
    cleaned = re.sub(r"  ", " ", cleaned)
    return cleaned.strip()


def text_normalize(rawstr):
    tnstring = rawstr.lower()
    tnstring = re.sub("[^a-z0-9':#,$-]", " ", tnstring)
    tnstring = re.sub("\\s+", " ", tnstring).strip()
    return tnstring


def basic_tokenizer(sentence):
    """Very basic tokenizer: split the sentence into a list of tokens."""
    words = []
    sentence_normed = text_normalize(sentence)
    # sentence_normed = sentence.lower()
    for space_separated_fragment in sentence_normed.split():
        words.extend(re.split(_WORD_SPLIT, space_separated_fragment))
    return [w for w in words if w]


def build_words_frequency_counter(vocabulary_data_dir, data_path, tokenizer=None):
    """
    Create vocabulary file (if it does not exist yet) from data file.
    Data file should have one sentence per line.
    Each sentence will be tokenized.
    Vocabulary contains the most-frequent tokens up to max_vocabulary_size.
    We write it to vocabulary_path in a one-token-per-line format, so that later
    token in the first line gets id=0, second line gets id=1, and so on.
    Args:
      vocabulary_path: path where the vocabulary will be created.
      data_path: data file that will be used to create vocabulary.
      max_vocabulary_size: limit on the size of the created vocabulary.
    """
    words_freq_counter_path = os.path.join(vocabulary_data_dir, "words_freq_counter")
    if not os.path.isfile(words_freq_counter_path):
        print("Building words frequency counter %s from data %s" % (words_freq_counter_path, data_path))

        def _word_generator():
            with open(data_path, 'r+') as f:
                for num, line in enumerate(f):
                    if num % 100000 == 0:
                        print("  processing line %d" % counter)
                    try:
                        tokens = tokenizer(line) if tokenizer else basic_tokenizer(line)
                    except Exception as e:
                        print("Tokenize failure: " + line)
                        continue
                    for word in tokens:
                        yield word

        counter = Counter(_word_generator())
        save_obj_pickle(counter, words_freq_counter_path, True)
        print('Vocabulary file created')


def pad_sequences(sequences, maxlen=None, dtype='int32',
                  padding='pre', truncating='pre', value=0.):
    """Pads each sequence to the same length (length of the longest sequence).
    If maxlen is provided, any sequence longer
    than maxlen is truncated to maxlen.
    Truncation happens off either the beginning (default) or
    the end of the sequence.
    Supports post-padding and pre-padding (default).
    # Arguments
        sequences: list of lists where each element is a sequence
        maxlen: int, maximum length
        dtype: type to cast the resulting sequence.
        padding: 'pre' or 'post', pad either before or after each sequence.
        truncating: 'pre' or 'post', remove values from sequences larger than
            maxlen either in the beginning or in the end of the sequence
        value: float, value to pad the sequences to the desired value.
    # Returns
        x: numpy array with dimensions (number_of_sequences, maxlen)
    # Raises
        ValueError: in case of invalid values for `truncating` or `padding`,
            or in case of invalid shape for a `sequences` entry.
    """
    if not hasattr(sequences, '__len__'):
        raise ValueError('`sequences` must be iterable.')
    lengths = []
    for x in sequences:
        if not hasattr(x, '__len__'):
            raise ValueError('`sequences` must be a list of iterables. '
                             'Found non-iterable: ' + str(x))
        lengths.append(len(x))

    num_samples = len(sequences)
    if maxlen is None:
        maxlen = np.max(lengths)

    # take the sample shape from the first non empty sequence
    # checking for consistency in the main loop below.
    sample_shape = tuple()
    for s in sequences:
        if len(s) > 0:
            sample_shape = np.asarray(s).shape[1:]
            break

    x = (np.ones((num_samples, maxlen) + sample_shape) * value).astype(dtype)
    for idx, s in enumerate(sequences):
        if not len(s):
            continue  # empty list/array was found
        if truncating == 'pre':
            trunc = s[-maxlen:]
        elif truncating == 'post':
            trunc = s[:maxlen]
        else:
            raise ValueError('Truncating type "%s" not understood' % truncating)

        # check `trunc` has expected shape
        trunc = np.asarray(trunc, dtype=dtype)
        if trunc.shape[1:] != sample_shape:
            raise ValueError('Shape of sample %s of sequence at position %s is different from expected shape %s' %
                             (trunc.shape[1:], idx, sample_shape))

        if padding == 'post':
            x[idx, :len(trunc)] = trunc
        elif padding == 'pre':
            x[idx, -len(trunc):] = trunc
        else:
            raise ValueError('Padding type "%s" not understood' % padding)
    return x


def find_ngrams(input_list, n):
    return zip(*[input_list[i:] for i in range(n)])


def trigram_encoding(data, trigram_dict, return_data=True):
    if data is None or len(data.strip()) == 0:
        data_triagrams_index = list()
        data = None
    else:
        refined_data = re.sub('[^a-z0-9.&\\ ]+', '', data.strip().lower())
        data_seq = refined_data.split()
        data_triagrams = list(chain(*[find_ngrams("#" + qw + "#", 3) for qw in data_seq]))
        data_triagrams_index = [trigram_dict[d] if d in trigram_dict else len(trigram_dict) + 1 for d in data_triagrams]
    result = data_triagrams_index, data if return_data else data_triagrams_index
    return result


# batch preparation of a given sequence pair for training
def prepare_train_pair_batch(seqs_x, seqs_y, source_maxlen=sys.maxsize, target_maxlen=sys.maxsize, dtype='int32'):
    # seqs_x, seqs_y: a list of sentences
    seqs_x = list(map(lambda x: x[:source_maxlen], seqs_x))
    seqs_y = list(map(lambda x: x[:target_maxlen], seqs_y))
    lengths_x = [len(s) for s in seqs_x]
    lengths_y = [len(s) for s in seqs_y]

    if len(lengths_x) < 1 or len(lengths_y) < 1:
        return None, None, None, None

    batch_size = len(seqs_x)

    x_lengths = np.array(lengths_x)
    y_lengths = np.array(lengths_y)

    maxlen_x = np.max(x_lengths)
    maxlen_y = np.max(y_lengths)

    x = np.ones((batch_size, maxlen_x)).astype(dtype) * end_token
    y = np.ones((batch_size, maxlen_y)).astype(dtype) * end_token

    for idx, [s_x, s_y] in enumerate(zip(seqs_x, seqs_y)):
        x[idx, :lengths_x[idx]] = s_x
        y[idx, :lengths_y[idx]] = s_y
    return x, x_lengths, y, y_lengths


# batch preparation of a given sequence for embedding or decoder
def prepare_train_batch(seqs, maxlen=None, dtype='int32'):
    # seqs_x, seqs_y: a list of sentences
    seqs = list(map(lambda x: x[:maxlen], seqs))
    lengths = [len(s) for s in seqs]

    if len(lengths) < 1:
        return None, None

    batch_size = len(seqs)

    lengths = np.array(lengths)

    maxlen = np.max(lengths)

    x = np.ones((batch_size, maxlen)).astype(dtype) * end_token

    for idx, s_x in enumerate(seqs):
        x[idx, :lengths[idx]] = s_x
    return x, lengths