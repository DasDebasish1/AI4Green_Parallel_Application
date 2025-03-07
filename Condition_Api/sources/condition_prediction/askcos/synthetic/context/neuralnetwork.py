import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()
import sources.condition_prediction.askcos.global_config as gc
import numpy as np
from tensorflow.keras.models import model_from_json
from tensorflow.keras import backend as K
import sources.condition_prediction.askcos.utilities.fingerprinting as fp
from sources.condition_prediction.askcos.utilities.io.logger import MyLogger
from sources.condition_prediction.askcos.interfaces.context_recommender import ContextRecommender
from scipy import stats
import pickle
from rdkit import Chem
import os
contextRecommender_loc = 'contextRecommender'


class NeuralNetContextRecommender(ContextRecommender):
    """Reaction condition predictor based on Neural Network method

    Attributes:
        nnModel ():
        c1_dict ():
        s1_dict ():
        s2_dict ():
        r1_dict ():
        r2_dict ():
        num_cond ():
        singleSlvt ():
        with_smiles ():
        max_total_context ():
        max_context ():
        fp_size ():
    """

    def __init__(self, max_contexts=10, singleSlvt=True, with_smiles=True):
        """Initializes Neural Network predictor.

        Args:
            max_contexts (int, optional): ?? (default: {10})
            singleSlvt (bool, optional): Whether to use only a single
                solvent. (default: {True})
            with_smiles (bool, optional): ?? (default: {True})
        """
        self.nnModel = None
        self.c1_dict = None
        self.s1_dict = None
        self.s2_dict = None
        self.r1_dict = None
        self.r2_dict = None
        self.num_cond = 1
        self.singleSlvt = singleSlvt
        self.with_smiles = with_smiles
        self.max_total_context = max_contexts
        self.max_context = 2
        self.fp_size = 2048

        # Solvent EHS score dictionary
        self.ehs_dict = {}

        self.session = tf.Session()
        tf.keras.backend.set_session(self.session)

    def load(self, model_path=gc.NEURALNET_CONTEXT_REC['model_path'], info_path=gc.NEURALNET_CONTEXT_REC[
                       'info_path'], weights_path=gc.NEURALNET_CONTEXT_REC['weights_path']):
        """Loads the specified model and weights.

        Wrapper function for ``load_nn_model``.

        Args:
            model_path (str, optional): Path to file specifying model.
                (default: {gc.NEURALNET_CONTEXT_REC['model_path']})
            info_path (str, optional): Path to file specifying encoders.
                (default: {gc.NEURALNET_CONTEXT_REC['info_path']})
            weights_path (str, optional): Path to file specifying weights.
                (default: {gc.NEURALNET_CONTEXT_REC['weights_path']})
        """
        # for the neural net model, info path points to the encoders
        self.load_nn_model(model_path, info_path, weights_path)
        self.load_ehs_dictionary(os.path.join(gc.data_path, 'solvents', 'ehs_solvent_scores.csv'))
        MyLogger.print_and_log(
            'Nerual network context recommender has been loaded.', contextRecommender_loc)

    def load_nn_model(self, model_path="", info_path="", weights_path=""):
        """Loads specified Neural Network model.

        Args:
            model_path (str, optional): Path to file specifying model.
                (default: {''})
            info_path (str, optional): Path to file specifying encoders.
                (default: {''})
            weights_path (str, optional): Path to file specifying weights.
                (default: {''})
        """
        if not model_path:
            MyLogger.print_and_log(
                'Cannot load neural net context recommender without a specific path to the model. Exiting...', contextRecommender_loc, level=3)
        if not info_path:
            MyLogger.print_and_log(
                'Cannot load nerual net context recommender without a specific path to the model info. Exiting...', contextRecommender_loc, level=3)

        ###load model##############
        # load json and create model
        K.set_learning_phase(0)
        json_file = open(model_path, 'r')
        loaded_model_json = json_file.read()
        json_file.close()

        self.nnModel = model_from_json(loaded_model_json)
        # load weights into new model
        self.nnModel.load_weights(weights_path)
        # get fp_size based on the model
        self.fp_size = self.nnModel.input_shape[0][1]
        r1_dict_file = info_path + "r1_dict.pickle"
        r2_dict_file = info_path + "r2_dict.pickle"
        s1_dict_file = info_path + "s1_dict.pickle"
        s2_dict_file = info_path + "s2_dict.pickle"
        c1_dict_file = info_path + "c1_dict.pickle"

        with open(r1_dict_file, "rb") as R1_DICT_F:
            self.r1_dict = pickle.load(R1_DICT_F)

        with open(r2_dict_file, "rb") as R2_DICT_F:
            self.r2_dict = pickle.load(R2_DICT_F)

        with open(s1_dict_file, "rb") as S1_DICT_F:
            self.s1_dict = pickle.load(S1_DICT_F)

        with open(s2_dict_file, "rb") as S2_DICT_F:
            self.s2_dict = pickle.load(S2_DICT_F)

        with open(c1_dict_file, "rb") as C1_DICT_F:
            self.c1_dict = pickle.load(C1_DICT_F)

        self.c1_dim = self.nnModel.input_shape[2][1]
        self.r1_dim = self.nnModel.input_shape[3][1]
        self.r2_dim = self.nnModel.input_shape[4][1]
        self.s1_dim = self.nnModel.input_shape[5][1]
        self.s2_dim = self.nnModel.input_shape[6][1]
        fp_transform_layer = self.nnModel.get_layer('fp_transform1')
        c1_input_layer = self.nnModel.get_layer('input_c1')
        s1_input_layer = self.nnModel.get_layer('input_s1')
        s2_input_layer = self.nnModel.get_layer('input_s2')
        r1_input_layer = self.nnModel.get_layer('input_r1')
        r2_input_layer = self.nnModel.get_layer('input_r2')
        c1_output = self.nnModel.get_layer('c1')
        s1_output = self.nnModel.get_layer('s1')
        s2_output = self.nnModel.get_layer('s2')
        r1_output = self.nnModel.get_layer('r1')
        r2_output = self.nnModel.get_layer('r2')
        T_output = self.nnModel.get_layer('T')

        self.fp_func = K.function(self.nnModel.inputs, [fp_transform_layer.output])
        self.c1_func = K.function([fp_transform_layer.output], [c1_output.output])
        self.s1_func = K.function([fp_transform_layer.output,c1_input_layer.output], [s1_output.output])
        self.s2_func = K.function([fp_transform_layer.output,c1_input_layer.output,s1_input_layer.output], [s2_output.output])
        self.r1_func = K.function([fp_transform_layer.output,c1_input_layer.output,s1_input_layer.output, s2_input_layer.output], [r1_output.output])
        self.r2_func = K.function([fp_transform_layer.output,c1_input_layer.output,s1_input_layer.output, s2_input_layer.output,r1_input_layer.output], [r2_output.output])
        self.T_func = K.function([fp_transform_layer.output,c1_input_layer.output,s1_input_layer.output, s2_input_layer.output,r1_input_layer.output,r2_input_layer.output], [T_output.output])

    def load_predictor(self, userInput):
        """Loads the predictor based on user input.

        Args:
            userInput (dict): Specifies values to use for the main attributes of
                the predictor.
        """
        self.num_cond = userInput['num_cond']
        self.dist_limit = userInput['dist_limit']
        self.singleSlvt = userInput['first_solvent_only']
        self.with_smiles = userInput['with_smiles_only']
        self.max_total_context = userInput['max_total_context']
        self.max_int = userInput['max_int']
        self.max_context = userInput['max_context']

    def get_n_conditions(self, rxn, n=10, singleSlvt=True, with_smiles=True, return_scores=False):
        """Returns the top n parseable reaction condition recommendations.

        Reaction condition recommendations for a rxn (SMILES) from top n NN

        Args:
            rxn (str): SMILES string for reaction.
            n (int, optional): Number of condition recomendations to return.
                (default: {10})
            singleSlvt (bool, optional): Whether to use a single solvent.
                (default: {true})
            with_smiles (bool, optional): ?? (default: {True})
            return_scores (bool, optional): Whether to also return the scores of the
                recomendations. (default: {True})
        """
        # print('started neuralnet')
        self.singleSlvt = singleSlvt
        self.with_smiles = with_smiles
        # print('rxn to recommend context for : {}'.format(rxn), contextRecommender_loc)
        try:
            rsmi = rxn.split('>>')[0]
            psmi = rxn.split('>>')[1]
            rct_mol = Chem.MolFromSmiles(rsmi)
            prd_mol = Chem.MolFromSmiles(psmi)
            [atom.ClearProp('molAtomMapNumber') for \
                    atom in rct_mol.GetAtoms() if atom.HasProp('molAtomMapNumber')]
            [atom.ClearProp('molAtomMapNumber') for \
                    atom in prd_mol.GetAtoms() if atom.HasProp('molAtomMapNumber')]
            rsmi = Chem.MolToSmiles(rct_mol, isomericSmiles=True)
            psmi = Chem.MolToSmiles(prd_mol, isomericSmiles=True)
            [pfp, rfp] = fp.create_rxn_Morgan2FP_separately(
                rsmi, psmi, rxnfpsize=self.fp_size, pfpsize=self.fp_size, useFeatures=False, calculate_rfp=True, useChirality=True)
            pfp = pfp.reshape(1, self.fp_size)
            rfp = rfp.reshape(1, self.fp_size)
            rxnfp = pfp - rfp
            c1_input = []
            r1_input = []
            r2_input = []
            s1_input = []
            s2_input = []
            inputs = [pfp, rxnfp, c1_input, r1_input,
                      r2_input, s1_input, s2_input]

            (top_combos,top_combo_scores)=self.predict_top_combos(inputs=inputs)

            top_combo_scores = list(map(float, top_combo_scores))

            if return_scores:
                return (self.contexts_ehs_scores(top_combos[:n]), top_combo_scores[:n])
            else:
                return self.contexts_ehs_scores(top_combos[:n])

        except Exception as e:

            # MyLogger.print_and_log('Failed for reaction {} because {}. Returning None.'.format(
            #     rxn, e), contextRecommender_loc, level=2)
            print('Failed for reaction {} because {}. Returning None.'.format(
                rxn, e), contextRecommender_loc)
            return [[]]

    def path_condition(self, n, path):
        """Recommends reaction conditions reaction path with multiple reactions.

        Args:
            n (int): Number of options to use at each step.
            path (list): Reaction SMILES for each step.


            Returns:
                A list of reaction contexts with n options for each step.
        """
        rsmi_list = []
        psmi_list = []
        contexts = []
        for rxn in path:
            try:
                rsmi = rxn.split('>>')[0]
                psmi = rxn.split('>>')[1]

                rct_mol = Chem.MolFromSmiles(rsmi)
                prd_mol = Chem.MolFromSmiles(psmi)
                [atom.ClearProp('molAtomMapNumber')for \
                        atom in rct_mol.GetAtoms() if atom.HasProp('molAtomMapNumber')]
                [atom.ClearProp('molAtomMapNumber')for \
                        atom in prd_mol.GetAtoms() if atom.HasProp('molAtomMapNumber')]
                rsmi = Chem.MolToSmiles(rct_mol, isomericSmiles=True)
                psmi = Chem.MolToSmiles(prd_mol, isomericSmiles=True)
                [pfp, rfp] = fp.create_rxn_Morgan2FP_separately(
                    rsmi, psmi, rxnfpsize=self.fp_size, pfpsize=self.fp_size, useFeatures=False, calculate_rfp=True, useChirality=True)
                pfp = pfp.reshape(1, self.fp_size)
                rfp = rfp.reshape(1, self.fp_size)
                rxnfp = pfp - rfp
                c1_input = []
                r1_input = []
                r2_input = []
                s1_input = []
                s2_input = []
                inputs = [pfp, rxnfp, c1_input, r1_input,
                          r2_input, s1_input, s2_input]
                top_combos = self.predict_top_combos(
                    inputs=inputs, c1_rank_thres=1, s1_rank_thres=3, s2_rank_thres=1, r1_rank_thres=4, r2_rank_thres=1)
                contexts.append(top_combos[:n])
            except Exception as e:
                MyLogger.print_and_log('Failed for reaction {} because {}. Returning None.'.format(
                    rxn, e), contextRecommender_loc, level=2)
        return contexts

    def predict_top_combos(self, inputs, return_categories_only = False,
                           c1_rank_thres=2, s1_rank_thres=3, s2_rank_thres=1,
                           r1_rank_thres=3, r2_rank_thres=1):
        """Predicts top combos based on rank thresholds for individual elements.

        Args:
            inputs (list??): Input values for model.
            return_categories_only (bool, optional): Whether to only return the
                categories. Used for testing. (default: {False})
            c1_rank_thres (int, optional): Rank threshold for c1??
                (default: {2})
            s1_rank_thres (int, optional): Rank threshold for s1??
                (default: {3})
            s2_rank_thres (int, optional): Rank threshold for s2??
                (default: {1})
            r1_rank_thres (int, optional): Rank threshold for r1??
                (default: {3})
            r2_rank_thres (int, optional): Rank threshold for r2??
                (default: {1})

        Returns:
            2-tuple of lists: Context combinations and scores predicted.
        """
        # this function predicts the top combos based on rank thresholds for
        # individual elements
        context_combos = []
        context_combo_scores = []
        num_combos = c1_rank_thres*s1_rank_thres * \
            s2_rank_thres*r1_rank_thres*r2_rank_thres
        [pfp, rxnfp, c1_input_user, r1_input_user,
            r2_input_user, s1_input_user, s2_input_user] = inputs

        # set s2 to be none ## specifically for the single sovlent case
        # s2_input_user = np.zeros(s2_dim,dtype = 'float32').reshape(1,s2_dim)
        # s2_input_user[0] = 1
        c1_input_dum = np.zeros(self.c1_dim, dtype='float32').reshape(1, self.c1_dim)
        r1_input_dum = np.zeros(self.r1_dim, dtype='float32').reshape(1, self.r1_dim)
        r2_input_dum = np.zeros(self.r2_dim, dtype='float32').reshape(1, self.r2_dim)
        s1_input_dum = np.zeros(self.s1_dim, dtype='float32').reshape(1, self.s1_dim)
        s2_input_dum = np.zeros(self.s2_dim, dtype='float32').reshape(1, self.s2_dim)
        model_inputs = [pfp, rxnfp, c1_input_dum, r1_input_dum,
                            r2_input_dum, s1_input_dum, s2_input_dum]
        with self.session.as_default():
            with self.session.graph.as_default():
                fp_trans = self.fp_func(model_inputs)
                if c1_input_user == []:
                    c1_inputs = fp_trans
                    c1_pred = self.c1_func(c1_inputs)
                    c1_cdts = c1_pred[0][0].argsort()[-c1_rank_thres:][::-1]
                else:
                    c1_cdts = np.nonzero(c1_input_user)[0]
                # find the name of catalyst
                for c1_cdt in c1_cdts:
                    c1_name = self.c1_dict[c1_cdt]
                    c1_input = np.zeros([1, self.c1_dim])
                    c1_input[0, c1_cdt] = 1
                    if c1_input_user == []:
                        c1_sc = c1_pred[0][0][c1_cdt]
                    else:
                        c1_sc = 1
                    if s1_input_user == []:
                        s1_inputs = [fp_trans[0],c1_input]
                        s1_pred = self.s1_func(s1_inputs)
                        s1_cdts = s1_pred[0][0].argsort()[-s1_rank_thres:][::-1]
                    else:
                        s1_cdts = np.nonzero(s1_input_user)[0]
                    for s1_cdt in s1_cdts:
                        s1_name = self.s1_dict[s1_cdt]
                        s1_input = np.zeros([1, self.s1_dim])
                        s1_input[0, s1_cdt] = 1
                        if s1_input_user == []:
                            s1_sc = s1_pred[0][0][s1_cdt]
                        else:
                            s1_sc = 1
                        if s2_input_user == []:
                            s2_inputs = [fp_trans[0], c1_input, s1_input]
                            s2_pred = self.s2_func(s2_inputs)
                            s2_cdts = s2_pred[0][0].argsort()[-s2_rank_thres:][::-1]
                        else:
                            s2_cdts = np.nonzero(s2_input_user)[0]
                        for s2_cdt in s2_cdts:
                            s2_name = self.s2_dict[s2_cdt]
                            s2_input = np.zeros([1, self.s2_dim])
                            s2_input[0, s2_cdt] = 1
                            if s2_input_user == []:
                                s2_sc = s2_pred[0][0][s2_cdt]
                            else:
                                s2_sc = 1
                            if r1_input_user == []:
                                r1_inputs = [fp_trans[0], c1_input, s1_input, s2_input]
                                r1_pred = self.r1_func(r1_inputs)
                                r1_cdts = r1_pred[0][
                                    0].argsort()[-r1_rank_thres:][::-1]
                            else:
                                r1_cdts = np.nonzero(r1_input_user)[0]
                            for r1_cdt in r1_cdts:
                                r1_name = self.r1_dict[r1_cdt]
                                r1_input = np.zeros([1, self.r1_dim])
                                r1_input[0, r1_cdt] = 1
                                if r1_input_user == []:
                                    r1_sc = r1_pred[0][0][r1_cdt]
                                else:
                                    r1_sc = 1
                                if r2_input_user == []:
                                    r2_inputs = [fp_trans[0], c1_input, s1_input, s2_input, r1_input]
                                    r2_pred = self.r2_func(r2_inputs)
                                    r2_cdts = r2_pred[0][
                                        0].argsort()[-r2_rank_thres:][::-1]
                                else:
                                    r2_cdts = np.nonzero(r2_input_user)[0]
                                for r2_cdt in r2_cdts:
                                    r2_name = self.r2_dict[r2_cdt]
                                    r2_input = np.zeros([1, self.r2_dim])
                                    r2_input[0, r2_cdt] = 1
                                    if r2_input_user == []:
                                        r2_sc = r2_pred[0][0][r2_cdt]
                                    else:
                                        r2_sc = 1
                                    T_inputs = [fp_trans[0], c1_input, s1_input, s2_input, r1_input, r2_input]
                                    T_pred = self.T_func(T_inputs)
                                    # print(c1_name,s1_name,s2_name,r1_name,r2_name)
                                    cat_name = [c1_name]
                                    if r2_name == '':
                                        rgt_name = [r1_name]
                                    else: rgt_name = [r1_name,r2_name]
                                    if s2_name == '':
                                        slv_name = [s1_name]
                                    else: slv_name = [s1_name,s2_name]
                                    # if self.with_smiles:
                                    #     rgt_name = [rgt for rgt in rgt_name if 'Reaxys' not in rgt]
                                    #     slv_name = [slv for slv in slv_name if 'Reaxys' not in slv]
                                    #     cat_name = [cat for cat in cat_name if 'Reaxys' not in cat]
                                    ##for testing purpose only, output order as training
                                    if return_categories_only:
                                        context_combos.append([c1_cdt,s1_cdt,s2_cdt,r1_cdt,r2_cdt,T_pred[0][0][0]])
                                    ## esle ouptupt format compatible with the overall framework
                                    else:
                                        context_combos.append(
                                            [float(T_pred[0][0][0]), '.'.join(slv_name), '.'.join(rgt_name), '.'.join(cat_name), np.nan, np.nan])

                                    context_combo_scores.append(
                                        c1_sc*s1_sc*s2_sc*r1_sc*r2_sc)
        context_ranks = list(num_combos+1 - stats.rankdata(context_combo_scores))

        context_combos = [context_combos[
            context_ranks.index(i+1)] for i in range(num_combos)]
        context_combo_scores = [context_combo_scores[
            context_ranks.index(i+1)] for i in range(num_combos)]

        return (context_combos, context_combo_scores)

    def category_to_name(self,chem_type,category):
        """Returns name ??

        Args:
            chem_type (str): ??
            category (??): ??
        """
        if chem_type == 'c1':
            return self.c1_dict[category]
        elif chem_type == 's1':
            return self.s1_dict[category]
        elif chem_type == 's2':
            return self.s2_dict[category]
        elif chem_type == 'r1':
            return self.r1_dict[category]
        elif chem_type == 'r2':
            return self.r2_dict[category]

    def load_ehs_dictionary(self, ehs_score_path):
        """
        #fills the attribute dictionary self.EHS_dict with solvent:EHS score pairs
        #assumes csv input file does not have any entrees that are not valid ASKCOS solvents
        #unscored solvents receive a score of 7
        #otherwise scores range 1-6;1 is best EHS score, 6 is worst

        Parameters
        ----------
        ehs_score_path : a route to a csv file pairing valid ASKCOS solvents with an EHS score
            DESCRIPTION.

        Returns
        -------
        None.

        """
        self.ehs_dict = {}
        with open(ehs_score_path, 'r') as f:
            for i, line in enumerate(f):
                if i == 0:
                    #Skip the first line (header)
                    continue
                a = line.strip().split(',') #Remove whitespace and split by commas
                key = a[2]
                value = a[3]
                if value.isdigit():
                    value = int(value)
                else:
                    value = 7
                self.ehs_dict[key] = value

    def contexts_ehs_scores(self, top_combos):
        """
        Takes a list of contexts for a reaction, as formatted by predict_top_combos,
        and adds to each context a solvent EHS score, and a boolean Best value

        """
        #find best score
        (a, best_score) = self.combo_ehs_score(top_combos)
        for item in top_combos:
            item.append(item[6] == best_score)
        return top_combos

    def combo_ehs_score(self, context_combos, best=True):
        """

        Parameters
        ----------
        context_combos : list of potential reaction conditions in the format 
                        returned by get.n.conditions prior to being edited for EHS scoring
        
            DESCRIPTION.
        best : Boolean;
                if True, returns first condition with best solvent score;
                if False, returns average solvent score of all conditions; 
                optional
            DESCRIPTION. The default is True.

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
              
        
        if best:
            best_score = 8
            best_combo = 'no solvents'
            for item in context_combos:
                solvent = item[1]
                if solvent in self.ehs_dict:
                    item.append(self.ehs_dict[solvent])
                    if self.ehs_dict[solvent] < best_score:
                        best_combo = item
                        best_score = self.ehs_dict[solvent]
                    else:
                        pass
                elif '.' in solvent: #if solvent is actually multiple solvents
                    solvents = solvent.split('.')
                    count = 0
                    score = 0
                    real_score = 8
                    for slv in solvents:
                        if slv in self.ehs_dict:
                            count += 1
                            score += self.ehs_dict[slv]
                    if count == 0:
                        real_score = 8
                    else:          
                        real_score = score / count
                    item.append(real_score)
                    if real_score < best_score:
                        best_combo = item
                        best_score = real_score
                    
                else:
                    item.append(None)
                    pass 
            return (best_combo, best_score)

        else:
            count = 0
            totalEHS = 0
            # if '' in self.EHS_dict:
            #     print ('empty string is a value :(')
            for item in context_combos:
                solvent = item[1]
                if solvent in self.ehs_dict:
                    count += 1
                    totalEHS += self.ehs_dict[solvent]
                    # print (count,totalEHS)
                elif '.' in solvent:
                    solvents = solvent.split('.')
                    count += 1
                    counter = 0
                    scoreer = 0
                    for slv in solvents:
                        if slv in self.ehs_dict:
                            counter += 1
                            scoreer += self.ehs_dict[slv]
                    if counter == 0:
                        count -= 1
                        continue
                    real_score = scoreer / counter
                    totalEHS += real_score
                else:
                    pass
            if count == 0:
                avg = 'no solvents'
            else:
                avg = totalEHS / count    
        
            return avg

if __name__ == '__main__':
    cont = NeuralNetContextRecommender()

    cont.load_nn_model(model_path=gc.NEURALNET_CONTEXT_REC['model_path'], info_path=gc.NEURALNET_CONTEXT_REC[
                       'info_path'], weights_path=gc.NEURALNET_CONTEXT_REC['weights_path'])
    print(cont.get_n_conditions('CC1(C)OBOC1(C)C.Cc1ccc(Br)cc1>>Cc1cccc(B2OC(C)(C)C(C)(C)O2)c1', 10, with_smiles=False, return_scores=True))
