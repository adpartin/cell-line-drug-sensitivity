""" 
This script generates multiple learning curves for different training sets.
It launches a script (e.g. trn_lrn_crv.py) that train ML model(s) on various training set sizes.
TODO: update the function trn_lrn_crv.py so that it will accept a df instead of the source names!
"""
# python -m pdb apps/lrn_crv/launch_lrn_crv.py
from __future__ import print_function, division

import warnings
warnings.filterwarnings('ignore')

import os
import sys
import platform
from pathlib import Path
import psutil
import argparse
from datetime import datetime
from time import time
from pprint import pprint, pformat
from collections import OrderedDict
from glob import glob

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import sklearn
import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler

SEED = 42


# File path
file_path = Path(__file__).resolve().parent


# Utils
utils_path = file_path / '../../utils'
sys.path.append(str(utils_path))
import utils
from utils_tidy import load_tidy_combined, get_data_by_src, break_src_data 
from classlogger import Logger
import ml_models
from cv_splitter import cv_splitter, plot_ytr_yvl_dist

# from lrn_crv import my_learning_curve
from lrn_crv_old import my_learning_curve


# Path
PRJ_NAME = file_path.name 
OUTDIR = file_path / '../../out/' / PRJ_NAME

        
def create_outdir(outdir, args, src):
    t = datetime.now()
    t = [t.year, '-', t.month, '-', t.day, '_', 'h', t.hour, '-', 'm', t.minute]
    t = ''.join([str(i) for i in t])
    
    l = [('cvf'+str(args['cv_folds']))] + args['cell_features'] + args['drug_features'] + [args['target_name']] 
    if 'nn' in args['model_name']:
        l = [args['opt']] + l
                
    name_sffx = '.'.join( [src] + [args['model_name']] + l )
    outdir = Path(outdir) / (name_sffx + '_' + t)
    os.makedirs(outdir)
    return outdir
    
        
        
def run(args):
    t0 = time()

    dirpath = Path(args['dirpath'])
    target_name = args['target_name']
    cv_folds = args['cv_folds']

    cell_fea = args['cell_features']
    drug_fea = args['drug_features']
    other_fea = args['other_features']
    fea_list = cell_fea + drug_fea + other_fea    

    epochs = args['epochs']
    batch_size = args['batch_size']
    dr_rate = args['dr_rate']
    opt_name = args['opt']

    lc_ticks = args['lc_ticks']

    model_name = args['model_name']
    n_jobs = args['n_jobs']

    # ML type ('reg' or 'cls')
    if 'reg' in model_name:
        mltype = 'reg'
    elif 'cls' in model_name:
        mltype = 'cls'
    else:
        raise ValueError('`model_name` must contain `reg` or `cls`.')

    # Define metrics
    metrics = {'r2': 'r2',
               'neg_mean_absolute_error': 'neg_mean_absolute_error', #sklearn.metrics.neg_mean_absolute_error,
               'neg_median_absolute_error': 'neg_median_absolute_error', #sklearn.metrics.neg_median_absolute_error,
               'neg_mean_squared_error': 'neg_mean_squared_error', #sklearn.metrics.neg_mean_squared_error,
               'reg_auroc_score': utils.reg_auroc_score,
    }
    
    
    # ========================================================================
    #       Load data and pre-proc
    # ========================================================================
    dfs = {}

    if dirpath is not None:
        if (dirpath/'xdata.parquet').is_file():
            xdata = pd.read_parquet( dirpath/'xdata.parquet', engine='auto', columns=None )
            meta = pd.read_parquet( dirpath/'meta.parquet', engine='auto', columns=None )
            ydata = meta[[target_name]]

        tr_id = pd.read_csv( dirpath/f'{cv_folds}fold_tr_id.csv' )
        vl_id = pd.read_csv( dirpath/f'{cv_folds}fold_vl_id.csv' )

        src = dirpath.name.split('_')[0]
        dfs[src] = (ydata, xdata, tr_id, vl_id) 
            
    elif dname == 'combined':
        # TODO: this is not used anymore (probably won't work)
        DATADIR = file_path / '../../data/processed/data_splits'
        DATAFILENAME = 'data.parquet'
        dirs = glob(str(DATADIR/'*'))
        
        for src in src_names:
            print(f'\n{src} ...')
            subdir = f'{src}_cv_{cv_method}'
            if str(DATADIR/subdir) in dirs:
                # Get the CV indexes
                tr_id = pd.read_csv(DATADIR/subdir/f'{cv_folds}fold_tr_id.csv')
                vl_id = pd.read_csv(DATADIR/subdir/f'{cv_folds}fold_vl_id.csv')

                # Get the data
                datapath = DATADIR / subdir / DATAFILENAME
                data = pd.read_parquet(datapath, engine='auto', columns=None)
                xdata, _, meta, _ = break_src_data(data, target=None, scaler=None) # logger=lg.logger
                ydata = meta[[target_name]]
                
                dfs[src] = (ydata, xdata, tr_id, vl_id)
                del data, xdata, ydata, tr_id, vl_id, src

    
    for src, data in dfs.items():
        ydata, xdata, tr_id, vl_id = data[0], data[1], data[2], data[3]

        # Scale 
        scaler = args['scaler']
        if scaler is not None:
            if scaler == 'stnd':
                scaler = StandardScaler()
            elif scaler == 'minmax':
                scaler = MinMaxScaler()
            elif scaler == 'rbst':
                scaler = RobustScaler()
        
        colnames = xdata.columns
        xdata = scaler.fit_transform(xdata).astype(np.float32)
        xdata = pd.DataFrame(xdata, columns=colnames)


        # -----------------------------------------------
        #       Logger
        # -----------------------------------------------
        run_outdir = create_outdir(OUTDIR, args, src)
        logfilename = run_outdir/'logfile.log'
        lg = Logger(logfilename)
        # lg.logger.info(datetime.now())
        lg.logger.info(f'\nFile path: {file_path}')
        # lg.logger.info(f'Machine: {platform.node()} ({platform.system()}, {psutil.cpu_count()} CPUs)')
        lg.logger.info(f'\n{pformat(args)}')

        # Dump args to file
        utils.dump_args(args, run_outdir)        


        # -----------------------------------------------
        #      ML model configurations
        # -----------------------------------------------
        lg.logger.info('\n\n{}'.format('=' * 50))
        lg.logger.info(f'Learning curves ... {src}')
        lg.logger.info('=' * 50)

        # ML model params
        if model_name == 'lgb_reg':
            init_kwargs = {'n_jobs': n_jobs, 'random_state': SEED, 'logger': lg.logger}
            fit_kwargs = {'verbose': False}  # 'early_stopping_rounds': 10,
        elif model_name == 'nn_reg':
            init_kwargs = {'input_dim': xdata.shape[1], 'dr_rate': dr_rate, 'opt_name': opt_name, 'attn': attn, 'logger': lg.logger}
            fit_kwargs = {'batch_size': batch_size, 'epochs': epochs, 'verbose': 1} 
        elif model_name == 'nn_reg0' or 'nn_reg1' or 'nn_reg2':
            init_kwargs = {'input_dim': xdata.shape[1], 'dr_rate': dr_rate, 'opt_name': opt_name, 'logger': lg.logger}
            fit_kwargs = {'batch_size': batch_size, 'epochs': epochs, 'verbose': 1}  # 'validation_split': 0.1
        elif model_name == 'nn_reg3' or 'nn_reg4':
            init_kwargs = {'in_dim_rna': None, 'in_dim_dsc': None, 'dr_rate': dr_rate, 'opt_name': opt_name, 'logger': lg.logger}
            fit_kwargs = {'batch_size': batch_size, 'epochs': epochs, 'verbose': 1}  # 'validation_split': 0.1


        # -----------------------------------------------
        #      Generate learning curve 
        # -----------------------------------------------
        lg.logger.info('\nStart learning curve (my method) ...')

        # Run learning curve
        t0 = time()
        lrn_crv_scores = my_learning_curve(
            X = xdata,
            Y = ydata,
            mltype = mltype,
            model_name = model_name,
            init_params = init_kwargs,
            fit_params = fit_kwargs,
            cv = None,
            cv_splits = (tr_id, vl_id),
            lc_ticks = lc_ticks,
            data_sz_frac = None,
            args = args,
            metrics = metrics,
            n_jobs = n_jobs, random_state = SEED, logger = lg.logger, outdir = run_outdir)
        lg.logger.info('Runtime: {:.1f} hrs'.format( (time()-t0)/3600) )

        lg.kill_logger()
        del xdata, ydata
        
    print('Done.')


def main(args):
    parser = argparse.ArgumentParser(description="Generate learning curves.")

    # Input data
    parser.add_argument('--dirpath', default=None, type=str,
        help='Full dir path to the data and split indices (default: None).')

    # Select target to predict
    parser.add_argument('-t', '--target_name',
        default='AUC', type=str, choices=['AUC', 'AUC1', 'IC50'],
        help='Column name of the target variable (default: AUC).')

    # Select feature types
    parser.add_argument('-cf', '--cell_features', nargs='+', default=['rna'], choices=['rna', 'cnv', 'clb'],
        help='Cell line features (default: `rna`).')
    parser.add_argument('-df', '--drug_features', nargs='+', default=['dsc'], choices=['dsc', 'fng', 'dlb'],
        help='Drug features (default: `dsc`).')
    parser.add_argument('-of', '--other_features', default=[], choices=[],
        help='Other feature types (derived from cell lines and drugs). E.g.: cancer type, etc).')

    # Data split methods
    parser.add_argument('-cvm', '--cv_method', default='simple', type=str, choices=['simple', 'group'],
        help='Cross-val split method (default: `simple`).')
    parser.add_argument('-cvf', '--cv_folds', default=5, type=str,
            help='Number cross-val folds (default: 5).')
    
    # ML models
    parser.add_argument('-ml', '--model_name', default='lgb_reg', type=str, 
        choices=['lgb_reg', 'rf_reg', 'nn_reg', 'nn_reg0', 'nn_reg1', 'nn_reg2', 'nn_reg3', 'nn_reg4'],
        help='ML model to use for training (default: `lgb_reg`).')

    # NN hyper_params
    parser.add_argument('-ep', '--epochs', default=200, type=int, help='Number of epochs (default: 200).')
    parser.add_argument('-b', '--batch_size', default=32, type=int, help='Batch size (default: 32).')
    parser.add_argument('--dr_rate', default=0.2, type=float, help='Dropout rate (default: 0.2).')
    parser.add_argument('-sc', '--scaler', default='stnd', type=str, choices=['stnd', 'minmax', 'rbst'],
        help='Normalization method of the features (default: `stnd`).')
    parser.add_argument('--opt', default='sgd', type=str, choices=['sgd', 'adam', 'clr'],
        help='Optimizer name (default: `sgd`).')

    # Learning curve
    parser.add_argument('--lc_ticks', default=5, type=int,
        help='Number of ticks in the learning curve plot default: 5).')

    # Define n_jobs
    parser.add_argument('--n_jobs', default=4, type=int, help='Default: 4.')

    # Parse args and run
    args = parser.parse_args(args)
    args = vars(args)
    ret = run(args)
    

if __name__ == '__main__':
    """ __name__ == '__main__' explained: www.youtube.com/watch?v=sugvnHA7ElY """
    main(sys.argv[1:])