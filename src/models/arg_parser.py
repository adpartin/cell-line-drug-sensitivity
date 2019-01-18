# Parsing priority: command-line > config-file > defualt params

import argparse
import configparser


# Default (arg, value) pairs for argparse object
dflt_args = {
    'target_name': 'AUC',
    'target_trasform': 'f',
    'train_sources': 'ccle',
    'test_sources': 'ccle',
    'tissue_type': None,
    'cell_features': 'rna', 
    'drug_features': 'dsc',
    'other_features': [] ,
    'ml_models': 'lgb_reg',
    'cv_method': 'simple',
    'cv_folds': 5,
    'verbose': 't',
    'n_jobs': 4
}


def get_args(args, config_fname):
    """ Main function that extracts arguments from command-line and config file.
    Args:
        args : args from command line.
        config_fname : config file name that contains (arg, value) pair. This will override the dflt_args.
    """
    parser = get_cli_args(args)
    config_params = read_config_file(file=config_fname)

    dflt_args_new = override_dflt_with_config(
        dflt_args=dflt_args,
        config_params=config_params)

    parser.set_defaults(**dflt_args_new)
    
    args = parser.parse_args(args)
    # args, unk_args = parser.parse_known_args(args)
    return args


def get_cli_args(args=None):
    """ Extracts args with argparse. """
    # Initialize parser
    parser = argparse.ArgumentParser(description="Cell-drug sensitivity parser.")

    # Select target to predict
    parser.add_argument("-t", "--target_name",
        # default="AUC",
        choices=["AUC", "AUC1", "IC50"],
        help="Column name of the target variable.") # target_name = 'AUC1'
    parser.add_argument("-tt", "--target_trasform",
        # default='f',
        choices=['t', 'f'], type=str_to_bool,
        help="'t': transform target, 'f': do not transform target.")

    # Select train and test (inference) sources
    parser.add_argument("-tr", "--train_sources", nargs="+",
        # default=["ccle"],
        choices=["ccle", "gcsi", "gdsc", "ctrp"],
        help="Data sources to use for training.")
    parser.add_argument("-te", "--test_sources", nargs="+",
        # default=["ccle"],
        choices=["ccle", "gcsi", "gdsc", "ctrp"],
        help="Data sources to use for testing.")

    # Select tissue types
    parser.add_argument('-ts', '--tissue_type',
        # default=argparse.SUPPRESS,
        choices=[],
        help='Tissue type to use.')

    # Select feature types
    parser.add_argument('-cf', '--cell_features', nargs='+',
        # default=['rna'],
        choices=['rna', 'cnv'],
        help='Cell line features.') # ['rna', cnv', 'rna_latent']
    parser.add_argument('-df', '--drug_features', nargs='+',
        # default=['dsc'],
        choices=['dsc', 'fng'],
        help='Drug features.') # ['dsc', 'fng', 'dsc_latent', 'fng_latent']
    parser.add_argument('-of', '--other_features',
        # default=[],
        choices=[],
        help='Other feature types (derived from cell lines and drugs). E.g.: cancer type, etc).') # ['cell_labels', 'drug_labels', 'ctype', 'csite', 'rna_clusters']

    # Select ML models
    parser.add_argument('-ml', '--ml_models',
        # default=["lgb_reg"],
        choices=['lgb_reg', 'rf_reg'],
        help='ML models to use for training.')

    # Select CV scheme
    parser.add_argument('-cvs', '--cv_method',
        # default="simple",
        choices=['simple', 'group'],
        help='Cross-val split method.')
    parser.add_argument('-cvf', '--cv_folds',
        # default=5,
        type=int,
        help='Number cross-val folds.')

    # Take care of utliers
    # parser.add_argument("--outlier", default=False)

    # Define verbosity
    parser.add_argument('-v', '--verbose',
        # default="t",
        choices=['t', 'f'], type=str_to_bool,
        help="'t': verbose, 'f': not verbose.")

    # Define n_jobs
    parser.add_argument('--n_jobs',
        # default=4,
        type=int)

    # Set deatuls from dict
    # parser.set_defaults(**defaults)

    # Parse the args
    # args = parser.parse_args(args)
    # args, unk_args = parser.parse_known_args(args)
    # return args
    return parser


def read_config_file(file):
    """ Read config file params.
    https://github.com/ECP-CANDLE/Benchmarks/blob/release_01/common/default_utils.py
    """
    config = configparser.ConfigParser()
    config.read(file)
    fileparams = {}
    
    for sec in config.sections():
        for param, value in config.items(sec):
            # if arg appear more than once in the file, use first one
            if not param in fileparams:
                fileparams[param] = eval(value)

    print('\nConfig file params:')
    print(fileparams)
    return fileparams


def override_dflt_with_config(dflt_args, config_params):
    """ Override default argparse arguments with parameters specified in config file.
    Args:
        dflt_args : dict with default arguments for argparse object
        config_params : dict with params from config file
    """
    for p, v in config_params.items():
        if p in dflt_args.keys():
            dflt_args[p] = v
        else:
            pass
    return dflt_args


# def args_overwrite_config(args, config_params):
#     """ Overwrite configuration parameters with parameters specified via command-line.    
#     Args:
#         args : ArgumentParser object (Parameters specified via command-line)
#         config_params : python dictionary (Parameters read from configuration file)
#     """
#     params = config_params
#     args_dict = vars(args)
#     for arg in args_dict.keys():
#         params[arg] = args_dict[arg]
#     return params


def str_to_bool(s):
    """ Convert string to bool (in argparse context).
    https://stackoverflow.com/questions/15008758/parsing-boolean-values-with-argparse
    """
    if s.lower() not in ['t', 'f']:
        raise ValueError("Need 't' or 'f'; got %r" % s)
    return {'t': True, 'f': False}[s.lower()]




