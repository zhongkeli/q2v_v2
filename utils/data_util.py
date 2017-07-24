# coding=utf-8
"""util for data processing"""
import sys
import re
import codecs
import string
import logging
from nltk import word_tokenize
from nltk.stem import WordNetLemmatizer
from enum import Enum, unique
import numpy as np
from config.config import end_token, unk_token

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


def find_ngrams(input_list, n):
    return zip(*[input_list[i:] for i in range(n)])


# batch preparation of a given sequence pair for training
def prepare_train_pair_batch(seqs_x, seqs_y, source_maxlen=sys.maxsize, target_maxlen=sys.maxsize, dtype='int32'):
    if len(seqs_x) != len(seqs_y):
        raise ValueError("Sequence lengths must be equal in their "
                         "batch_size, %d != %d" % (len(seqs_x), len(seqs_y)))
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


# parse aksis query pair data

def parse_aksis_query_data(line):
    queries = [] if line is None else line.split("\t")
    if len(queries) < 2:
        return list()
    tokens_list = list()
    for query in queries[1:]:
        tokens = tokenize(query)
        tokens_list.extend(tokens)

    return tokens_list


def data_encoding(data, vocabulary, ngram=3, return_data=True):
    data_index = list()
    if data and len(data.strip()) > 0:
        words = tokenize(data)
        for word in words:
            if word in vocabulary:
                data_index.extend(words_index_lookup(word, vocabulary))
            else:
                words_list = ngram_tokenize_word(word, ngram)
                data_index.extend(words_index_lookup(words_list, vocabulary))

    result = data_index, data if return_data else data_index

    return result


def ngram_tokenize_word(word, ngram):
    word = re.sub('[^a-z0-9#.\'-, ]+', '', word.strip().lower())
    words_list = [''.join(ele) for ele in find_ngrams('#' + word + '#', ngram)]
    return words_list


def words_index_lookup(words_list, vocabulary):
    if not isinstance(words_list, list):
        words_list = [words_list]
    words_index = [vocabulary[d] if d in vocabulary else unk_token for d in words_list]
    return words_index


def extract_siamese_data(line):
    line = re.sub(r'(?:^\(|\)$)', '', line)
    line = line.strip().lower()
    items = re.split(r'\t+', line)
    if len(items) == 3:
        return items[0], items[1], items[2]
    else:
        return None, None, None


def siamese_data_generator(files):
    for sentence in sentence_gen(files):
        try:
            data = extract_siamese_data(sentence)
            yield data
        except Exception as e:
            logging.error("Failed to extract siamese data %s", sentence, exc_info=True, stack_info=True)
