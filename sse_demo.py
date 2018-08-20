# coding=utf-8
################################################################################
#
# Copyright (c) 2016 eBay Software Foundation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#################################################################################
#
# @Author: Mingkuan Liu
# @Email:  mingkliu@ebay.com
# @Date:   2016-07-24
#
##################################################################################


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

# from builtins import str
from builtins import str
from builtins import range
import os
import sys
import time

import numpy as np
import tensorflow as tf

import data_utils
import sse_model
import text_encoder
import codecs


tf.app.flags.DEFINE_string("device", "0", "Default to use GPU:0. Softplacement used, if no GPU found, further default to cpu:0.")
tf.app.flags.DEFINE_string("model_dir", 'models-classification', "Trained model directory.")
tf.app.flags.DEFINE_string("indexFile", 'targetEncodingIndex.tsv', "Index file contains target space semantic embedding vectors. Must placed within model_dir.")


FLAGS = tf.app.flags.FLAGS

os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"]=FLAGS.device  # value can be 0,1,2, 3


def demo(nbest):
  if not os.path.exists( FLAGS.model_dir ):
    print('Model folder does not exist!!')
    exit(-1)

  if not os.path.exists( os.path.join( FLAGS.model_dir, 'vocabulary.txt' ) ):
    print('Error!! Could not find vocabulary file for encoder in model folder.')
    exit(-1)
  encoder = text_encoder.SubwordTextEncoder(filename=os.path.join(FLAGS.model_dir, 'vocabulary.txt' ))

  if not os.path.exists( os.path.join( FLAGS.model_dir, FLAGS.indexFile) ):
    print('Index file does not exist!!!')
    exit(-1)

  #load full set target Index data
  targetEncodings = []
  targetIDs = []
  idLabelMap = {}
  targetIDNameMap = {}
  idx=0
  for line in codecs.open( os.path.join( FLAGS.model_dir, FLAGS.indexFile), 'rt', 'utf-8').readlines():
    info = line.strip().split('\t')
    if len(info) != 3:
      print('Error in targetIndexFile! %s' % line)
      continue
    tgtid, tgtseq, tgtEncoding = info[0], info[1], info[2]
    targetIDs.append(tgtid)
    targetEncodings.append( [ float(f) for f in tgtEncoding.strip().split(',') ] )
    idLabelMap[tgtid] = idx
    targetIDNameMap[tgtid] = tgtseq
    idx += 1
  targetEncodings = np.array(targetEncodings)

  cfg = tf.ConfigProto(log_device_placement=False, allow_soft_placement=True)
  with tf.Session(config=cfg) as sess:
    # TODO: improve here later
    #load model
    modelConfigs = data_utils.load_model_configs(FLAGS.model_dir)
    model = sse_model.SSEModel( modelConfigs )
    ckpt = tf.train.get_checkpoint_state(FLAGS.model_dir)
    if ckpt:
      print("Reading model parameters from %s" % ckpt.model_checkpoint_path)
      model.saver.restore(sess, ckpt.model_checkpoint_path)
    else:
        print('Error!!!Could not load any model from specified folder: %s' % FLAGS.model_dir)
        exit(-1)

    # Decode from standard input.
    sys.stdout.write("\n\nPlease type some keywords to get related task results.\nType 'exit' to quit demo.\n > ")
    sys.stdout.flush()
    sentence = sys.stdin.readline()
    while sentence and sentence.strip().lower() != 'exit':
      # Get token-ids for the input sentence.
      source_tokens = encoder.encode( tf.compat.as_str(sentence).lower())
      srclen = len(source_tokens)
      max_seq_length = int(modelConfigs['max_seq_length'])
      if srclen > max_seq_length - 2:
        print('Input sentence too long, max allowed is %d. Try to increase limit!!!!' % (max_seq_length))
        source_tokens = [text_encoder.PAD_ID] + source_tokens[:max_seq_length - 2] + [text_encoder.EOS_ID]
      else:
        source_tokens = [text_encoder.PAD_ID] * (max_seq_length - srclen - 1) + source_tokens + [text_encoder.EOS_ID]

      feed_dict = model.get_source_encoding_feed_dict(np.array([source_tokens]))
      model.set_forward_only(True)
      sourceEncodings = sess.run( [model.src_seq_embedding], feed_dict= feed_dict )
      #sourceEncodings = sess.run([model.norm_src_seq_embedding], feed_dict=feed_dict)
      sourceEncodings = np.vstack(sourceEncodings)
      distances = np.dot(sourceEncodings, targetEncodings.T)
      rankedScore, rankedIdx = data_utils.getSortedResults(distances)
      top_confs = rankedScore[0][:nbest]
      top_tgtIDs = [ targetIDs[lbl] for lbl in rankedIdx[0][:nbest]]
      top_tgtNames = [ targetIDNameMap[id] for id in top_tgtIDs ]

      print('Top %s Prediction results are:\n' % nbest)
      for idx in range(nbest):
        print( 'top%d:  %s , %f ,  %s ' % ( idx+1, top_tgtIDs[idx],  top_confs[idx], top_tgtNames[idx]) )
      print("> ", end="")

      sys.stdout.flush()
      sentence = sys.stdin.readline()


def main(_):
  if not FLAGS.model_dir:
    print("--model_dir must be specified.")
    sys.exit(1)

  demo(int(sys.argv[1]))


if __name__ == "__main__":
  tf.app.run()
