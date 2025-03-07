import os
import sources.condition_prediction.askcos.global_config as gc
from pymongo import MongoClient
from sources.condition_prediction.askcos.utilities.io.logger import MyLogger
from sources.condition_prediction.askcos.utilities.buyable.pricer import Pricer
from sources.condition_prediction.askcos.synthetic.context.nearestneighbor import NNContextRecommender
from sources.condition_prediction.askcos.synthetic.context.neuralnetwork import NeuralNetContextRecommender
from sources.condition_prediction.askcos.synthetic.enumeration.transformer import ForwardTransformer
from sources.condition_prediction.askcos.retrosynthetic.transformer import RetroTransformer
# from sources.condition_prediction.askcos.synthetic.evaluation.template_based import TemplateNeuralNetScorer
from sources.condition_prediction.askcos.synthetic.evaluation.template_free import TemplateFreeNeuralNetScorer
from sources.condition_prediction.askcos.synthetic.evaluation.fast_filter import FastFilterScorer
import sys
model_loader_loc = 'model_loader'


def load_Retro_Transformer():
    '''    
    Load the model and databases required for the retro transformer. Returns the retro transformer, ready to run.
    '''
    MyLogger.print_and_log(
        'Loading retro synthetic template database...', model_loader_loc)
    retroTransformer = RetroTransformer()
    retroTransformer.load()
    MyLogger.print_and_log(
        'Retro synthetic transformer loaded.', model_loader_loc)
    return retroTransformer


def load_Pricer(chemical_database, buyable_database):
    '''
    Load a pricer using the chemicals database and database of buyable chemicals
    '''
    MyLogger.print_and_log('Loading pricing model...', model_loader_loc)
    pricerModel = Pricer()
    pricerModel.load(chemical_database, buyable_database)
    MyLogger.print_and_log('Pricer Loaded.', model_loader_loc)
    return pricerModel


def load_Forward_Transformer(mincount=100, worker_no = 0):
    '''
    Load the forward prediction neural network
    '''
    if worker_no==0:
        MyLogger.print_and_log('Loading forward prediction model...', model_loader_loc)
    transformer = ForwardTransformer()
    transformer.load(worker_no = worker_no)
    if worker_no==0:
        MyLogger.print_and_log('Forward transformer loaded.', model_loader_loc)
    return transformer


def load_fastfilter():
    ff = FastFilterScorer()
    ff.load(model_path =gc.FAST_FILTER_MODEL['model_path'])
    return ff


def load_templatebased(mincount=25, celery=False, worker_no = 0):
#     transformer = None
#     if not celery:
#         transformer = load_Forward_Transformer(mincount=mincount, worker_no = worker_no)
#     scorer = TemplateNeuralNetScorer(forward_transformer=transformer, celery=celery)
#     scorer.load(gc.PREDICTOR['trained_model_path'], worker_no = worker_no)
#     return scorer
    return None


def load_templatefree():
    # Still has to be implemented
    return TemplateFreeNeuralNetScorer()


def load_Context_Recommender(context_recommender, max_contexts=10):
    '''
    Load the context recommendation model
    '''
    MyLogger.print_and_log('Loading context recommendation model: {}...'.format(
        context_recommender), model_loader_loc)
    if context_recommender == gc.nearest_neighbor:
        recommender = NNContextRecommender(max_contexts=max_contexts)
        recommender.load(model_path=gc.CONTEXT_REC[
                         'model_path'], info_path=gc.CONTEXT_REC['info_path'])
    elif context_recommender == gc.neural_network:
        recommender = NeuralNetContextRecommender(max_contexts=max_contexts)
        recommender.load(model_path=gc.NEURALNET_CONTEXT_REC['model_path'], info_path=gc.NEURALNET_CONTEXT_REC[
                       'info_path'], weights_path=gc.NEURALNET_CONTEXT_REC['weights_path'])
    else:
        raise NotImplementedError
    MyLogger.print_and_log('Context recommender loaded.', model_loader_loc)
    return recommender
