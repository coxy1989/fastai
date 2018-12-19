"Tools to help find the optimal learning rate for training"
from ..torch_core import *
from ..basic_data import DataBunch
from ..callback import *
from ..basic_train import Learner, LearnerCallback, validate

__all__ = ['LRFinder', 'LRFinderPlus']

class LRFinder(LearnerCallback):
    "Causes `learn` to go on a mock training from `start_lr` to `end_lr` for `num_it` iterations."
    def __init__(self, learn:Learner, start_lr:float=1e-7, end_lr:float=10, num_it:int=100, stop_div:bool=True):
        super().__init__(learn)
        self.data,self.stop_div = learn.data,stop_div
        self.sched = Stepper((start_lr, end_lr), num_it, annealing_exp)
        #To avoid validating if the train_dl has less than num_it batches, we put aside the valid_dl and remove it
        #during the call to fit.
        self.valid_dl = learn.data.valid_dl
        self.data.valid_dl = None

    def on_train_begin(self, pbar, **kwargs:Any)->None:
        "Initialize optimizer and learner hyperparameters."
        setattr(pbar, 'clean_on_interrupt', True)
        self.learn.save('tmp')
        self.opt = self.learn.opt
        self.opt.lr = self.sched.start
        self.stop,self.best_loss = False,0.

    def on_batch_end(self, iteration:int, smooth_loss:TensorOrNumber, **kwargs:Any)->None:
        "Determine if loss has runaway and we should stop."
        if iteration==0 or smooth_loss < self.best_loss: self.best_loss = smooth_loss
        self.opt.lr = self.sched.step()
        if self.sched.is_done or (self.stop_div and (smooth_loss > 4*self.best_loss or torch.isnan(smooth_loss))):
            #We use the smoothed loss to decide on the stopping since it's less shaky.
            self.stop=True
            return True

    def on_epoch_end(self, **kwargs:Any)->None:
        "Tell Learner if we need to stop."
        return self.stop

    def on_train_end(self, **kwargs:Any)->None:
        "Cleanup learn model weights disturbed during LRFind exploration."
        # restore the valid_dl we turned off on `__init__`
        self.data.valid_dl = self.valid_dl
        self.learn.load('tmp')
        if hasattr(self.learn.model, 'reset'): self.learn.model.reset()
        print('LR Finder is complete, type {learner_name}.recorder.plot() to see the graph.')

class LRFinderPlus(LearnerCallback):
    
    def __init__(self, learn:Learner, start_lr:float=1e-7, end_lr:float=10, num_it:int=100, stop_div:bool=True):
        super().__init__(learn)
        self.data,self.stop_div = learn.data,stop_div
        self.sched = Stepper((start_lr, end_lr), num_it, annealing_exp)
        #To avoid validating if the train_dl has less than num_it batches, we put aside the valid_dl and remove it
        #during the call to fit.
        self.valid_dl = learn.data.valid_dl
        self.data.valid_dl = None
        self.smoothener = SmoothenValue(0.98)

    def on_train_begin(self, pbar, **kwargs:Any)->None:
        "Initialize optimizer and learner hyperparameters."
        setattr(pbar, 'clean_on_interrupt', True)
        self.learn.save('tmp')
        self.opt = self.learn.opt
        self.opt.lr = self.sched.start
        self.stop,self.best_val_loss, self.best_trn_loss = False,0.,0.
        self.pbar = pbar

    def on_batch_end(self, iteration:int, smooth_loss:TensorOrNumber, train=True, **kwargs:Any)->None:
        val_losses = validate(self.learn.model, self.valid_dl, self.learn.loss_func, CallbackHandler([], []), pbar=self.pbar)
        self.smoothener.add_value(val_losses)
        self.learn.recorder.val_losses.append(self.smoothener.smooth)
        if iteration==0 or smooth_loss < self.best_trn_loss: self.best_trn_loss = smooth_loss
        if iteration==0 or self.smoothener.smooth < self.best_val_loss: self.best_val_loss = self.smoothener.smooth
        self.opt.lr = self.sched.step()
        if self.sched.is_done or (self.stop_div and (self.smoothener.smooth > 4*self.best_val_loss)):
            #We use the smoothed loss to decide on the stopping since it's less shaky.
            self.stop=True
            return True

    def on_epoch_end(self, **kwargs:Any)->None:
        "Tell Learner if we need to stop."
        return self.stop

    def on_train_end(self, **kwargs:Any)->None:
        "Cleanup learn model weights disturbed during LRFind exploration."
        # restore the valid_dl we turned off on `__init__`
        self.data.valid_dl = self.valid_dl
        self.learn.load('tmp')
        if hasattr(self.learn.model, 'reset'): self.learn.model.reset()
        print('LR Finder is complete, type {learner_name}.recorder.plot() to see the graph.')
    
