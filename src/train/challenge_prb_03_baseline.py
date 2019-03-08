from __future__ import print_function, division

import warnings
warnings.filterwarnings('ignore')

# from comet_ml import Experiment
import os

import sys
import pathlib
import argparse
import datetime
from time import time
from pprint import pprint
from glob import glob

import sklearn
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import keras as ke
from keras import backend as K

from keras.models import Sequential, Model, model_from_json, model_from_yaml, load_model
from keras.optimizers import SGD, Adam, RMSprop, Adadelta
from keras.utils import np_utils, multi_gpu_model
from keras.callbacks import Callback, ModelCheckpoint, CSVLogger, ReduceLROnPlateau, EarlyStopping

from sklearn.preprocessing import StandardScaler
from sklearn.externals import joblib

from sklearn.model_selection import train_test_split
from sklearn.model_selection import ShuffleSplit, KFold # (AP)
from sklearn.model_selection import GroupShuffleSplit, GroupKFold # (AP)
from sklearn.model_selection import StratifiedShuffleSplit, StratifiedKFold # (AP)

SEED = None
t_start = time()


# Utils
import ml_models
import classlogger
import utils


# Import custom callbacks
keras_contrib = '/vol/ml/apartin/projects/keras-contrib/keras_contrib'
sys.path.append(keras_contrib)
from callbacks import *


# File path
# file_path = os.path.dirname(os.path.realpath(__file__))
file_path = pathlib.Path(__file__).resolve().parent


# Path - create dir to dump results (AP)
PRJ_NAME = 'candle_challenge_prb'
PHASE = 'baseline'
OUTDIR = file_path / '../../models' / PRJ_NAME / PHASE
os.makedirs(OUTDIR, exist_ok=True)

DATADIR = file_path / '../../models' / PRJ_NAME / 'data'
WRMDIR = file_path / '../../models' / PRJ_NAME / 'wrm'


# Arg parser
psr = argparse.ArgumentParser(description='input agg csv file')
psr.add_argument('--batch', type=int, default=32)
psr.add_argument('-dr', '--dr_rate',type=float, default=0.2)
psr.add_argument('--attn',  type=int, default=0, choices=[0, 1]) # (AP)
# psr.add_argument('--n_jobs',  type=int, default=4) # (AP)
psr.add_argument('-ml', '--model_name',  type=str, default='nn_reg') # (AP)
psr.add_argument('--ep', type=int, default=250, help='Total number epochs')
# psr.add_argument('--lr',  type=float, default=0.0005, help='Learning rate')
psr.add_argument('--split_method', type=str, choices=['rnd', 'hrd'], default='hrd')
psr.add_argument('--skip_ep', type=int, default=3, help='Number of epochs to skip when plotting training curves.')

args = vars(psr.parse_args())
pprint(args)


# Args
EPOCH = args['ep']
BATCH = args['batch']
DR = args['dr_rate']
# LR = args['lr']
attn = bool(args['attn'])
model_name = args['model_name']
split_method = args['split_method']
skip_epochs = args['skip_ep']


# Data path
if split_method == 'rnd':
    data_path = DATADIR / 'rnd' / 'df_cnt.parquet'
    outdir = OUTDIR / 'rnd'
    wrmdir = WRMDIR / 'rnd'
elif split_method == 'hrd':
    data_path = DATADIR / 'hrd' / 'df_cnt.parquet'
    outdir = OUTDIR / 'hrd'
    wrmdir = WRMDIR / 'hrd'
os.makedirs(outdir, exist_ok=True)


# Dump args
utils.dump_args(args, outdir=outdir)


# Create logger
logfilename = outdir / 'logfile.log'
lg = classlogger.Logger(logfilename=logfilename) 


# Custom metrics
def r2(y_true, y_pred):
    SS_res =  K.sum(K.square(y_true - y_pred))
    SS_tot = K.sum(K.square(y_true - K.mean(y_true)))
    return (1 - SS_res/(SS_tot + K.epsilon()))

    
# ---------
# Load data
# ---------
lg.logger.info(f'Loading data ... {data_path}')
t0 = time()
df = pd.read_parquet(data_path, engine='auto', columns=None)
df = df.sample(frac=1.0, axis=0, random_state=SEED)
lg.logger.info('Done ({:.2f} mins).\n'.format((time()-t0)/60))


# ---------------------------
# Extract features and target
# ---------------------------
dfy, dfx = df.iloc[:, 0], df.iloc[:, 1:];  del df


# -------------------
# Split to train/text
# -------------------
xtr, xte, ytr, yte = train_test_split(dfx, dfy)
lg.logger.info('xtr.shape: {}'.format(xtr.shape))
lg.logger.info('xte.shape: {}'.format(xte.shape))
lg.logger.info('ytr.shape: {}'.format(ytr.shape))
lg.logger.info('yte.shape: {}'.format(yte.shape))

# Dump dfs
lg.logger.info('\nDump dfs ...')
df_tr = pd.concat([ytr, xtr], axis=1)
df_te = pd.concat([yte, xte], axis=1)
df_tr.to_parquet(outdir/'df_tr.parquet', engine='auto', compression='snappy')
df_te.to_parquet(outdir/'df_te.parquet', engine='auto', compression='snappy')

# Scale
scaler_path = wrmdir/'scaler.pkl'
scaler = joblib.load(scaler_path)
xtr = pd.DataFrame( scaler.transform(xtr) ).astype(np.float32)
xte = pd.DataFrame( scaler.transform(xte) ).astype(np.float32)


# ----------------------
# Train 'baseline' model
# ----------------------
tag = 'baseline'

# Callbacks (custom)
clr_triangular = CyclicLR(base_lr=0.0001, max_lr=0.001, mode='triangular')

# Keras callbacks
reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.75, patience=20, verbose=1, mode='auto',
                              min_delta=0.0001, cooldown=3, min_lr=0.000000001)
early_stop = EarlyStopping(monitor='val_loss', patience=60, verbose=1, mode='auto')
checkpointer = ModelCheckpoint(str(outdir / 'model.baseline.ep_{epoch:d}-val_loss_{val_loss:.5f}.h5'), verbose=0, save_weights_only=False, save_best_only=False)
csv_logger = CSVLogger(outdir / f'model.{tag}.log')
callback_list = [checkpointer, csv_logger, early_stop, reduce_lr]

# Callbacks list
callback_list = [checkpointer, csv_logger, early_stop, reduce_lr,  # keras callbacks
                 clr_triangular]  # custom callbacks

# fit_params
fit_params = {'batch_size': BATCH, 'epochs': EPOCH, 'verbose': 1}
fit_params['validation_data'] = (xte, yte)
fit_params['callbacks'] = callback_list

# Get the estimator
init_params = {'input_dim': dfx.shape[1], 'dr_rate': DR, 'attn': attn}
# init_params = {'input_dim': dfx.shape[1], 'dr_rate': DR, 'attn': attn, 'lr': LR}
model = ml_models.get_model(model_name=model_name, init_params=init_params)

# Train model - baseline phase
t0 = time()
history = model.model.fit(xtr, ytr, **fit_params)
fit_runtime = time() - t0
lg.logger.info('fit_runtime: {:.3f} mins'.format(fit_runtime/60))

# Print score
score = model.model.evaluate(xte, yte, verbose=0)
lg.logger.info('val_loss: {:.5f}'.format(score[0]))

# Print plots
model_plts_path = outdir / f'model_{tag}_plts'
os.makedirs(model_plts_path, exist_ok=True)
ml_models.plot_prfrm_metrics(history=history,
                             title=f'Baseline training',  # LR: {LR}
                             skip_epochs=skip_epochs,
                             add_lr=True,
                             outdir=model_plts_path)

# Dump history
pd.DataFrame(history.history).to_csv(outdir/'keras_history.csv', index=False)

# Define path to dump model and weights
model_path = outdir / f'model.{tag}.json'
weights_path = outdir / f'weights.{tag}.h5'

# Save model
model_json = model.model.to_json()
with open(model_path, 'w') as json_file:
    json_file.write(model_json)

# Save weights
model.model.save_weights(weights_path)

lg.logger.info('\nProgram runtime: {:.2f} mins'.format( (time() - t_start)/60 ))
lg.logger.info('Done.')


