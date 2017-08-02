import glob
import argparse
import os
import signal
import sys

import logging.config
import yaml
from utils.config_decouple import config
from helper.data_record_helper import DataRecordHelper

from helper.data_parser import QueryPairParser


def parse_args():
    parser = argparse.ArgumentParser(description='Vocabulary tools')

    parser.add_argument('-tp', '--tfrecord-path', type=str, default=os.path.join(config('traindata_dir'), 'train.tfrecords'),
                                  help='path for tfrecord train data')
    parser.add_argument('-mw', '--min-words', type=int, default=2, help='ignore the sequence that length < min_words')
    parser.add_argument('file_pattern', type=str, help='the corpus input files pattern')

    return parser.parse_args()


def signal_handler(signal, frame):
    logging.info('Stop!!!')
    sys.exit(0)


def setup_logger():
    logging_config_path = config('logging_config_path')
    with open(logging_config_path) as f:
        dictcfg = yaml.load(f)
        logging.config.dictConfig(dictcfg)


if __name__ == "__main__":
    args = parse_args()
    setup_logger()
    signal.signal(signal.SIGINT, signal_handler)
    parser = QueryPairParser()
    files = glob.glob(args.file_pattern)
    d = DataRecordHelper()
    gen = parser.siamese_sequences_to_tokens_generator(files, args.min_words)
    d.create_sequence(gen, record_path=args.tfrecord_path)
