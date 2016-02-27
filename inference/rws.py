'''
Reweighted wake-sleep inference
'''

from collections import OrderedDict
import theano
from theano import tensor as T

from utils import floatX
from utils.tools import (
    log_sum_exp,
    warn_kwargs
)


class RWS(object):
    def __init__(self,
                 model,
                 name='RWS',
                 **kwargs):
        self.name = name
        self.model = model
        warn_kwargs(self, **kwargs)

    def __call__(self, x, y, n_posterior_samples=10, qk=None):
        model = self.model

        print 'Doing RWS, %d samples' % n_posterior_samples
        q   = model.posterior.feed(x)

        if qk is None:
            q_c = q.copy()
        else:
            q_c = qk

        r  = model.trng.uniform((n_posterior_samples, y.shape[0], model.dim_h), dtype=floatX)
        h  = (r <= q_c[None, :, :]).astype(floatX)
        py = model.conditional.feed(h)

        log_py_h = -model.conditional.neg_log_prob(y[None, :, :], py)
        log_ph   = -model.prior.neg_log_prob(h)
        log_qh   = -model.posterior.neg_log_prob(h, q[None, :, :])

        assert log_py_h.ndim == log_ph.ndim == log_qh.ndim

        if qk is None:
            log_p = log_sum_exp(log_py_h + log_ph - log_qh, axis=0) - T.log(n_posterior_samples)
        else:
            log_qkh = -model.posterior.neg_log_prob(h, qk[None, :, :])
            log_p = log_sum_exp(log_py_h + log_ph - log_qkh, axis=0) - T.log(n_posterior_samples)

        log_pq   = log_py_h + log_ph - log_qh - T.log(n_posterior_samples)
        w_norm   = log_sum_exp(log_pq, axis=0)
        log_w    = log_pq - T.shape_padleft(w_norm)
        w_tilde  = T.exp(log_w)

        y_energy      = -(w_tilde * log_py_h).sum(axis=0)
        prior_energy  = -(w_tilde * log_ph).sum(axis=0)
        h_energy      = -(w_tilde * log_qh).sum(axis=0)

        nll           = -log_p
        prior_entropy = model.prior.entropy()
        q_entropy     = model.posterior.entropy(q_c)

        assert prior_energy.ndim == h_energy.ndim == y_energy.ndim, (prior_energy.ndim, h_energy.ndim, y_energy.ndim)

        cost = (y_energy + prior_energy + h_energy).sum(0)
        lower_bound = (y_energy + prior_energy - q_entropy).mean()

        results = OrderedDict({
            '-log p(x|h)': y_energy.mean(0),
            '-log p(h)': prior_energy.mean(0),
            '-log q(h)': h_energy.mean(0),
            '-log p(x)': nll.mean(0),
            'H(p)': prior_entropy,
            'H(q)': q_entropy.mean(0),
            'lower_bound': lower_bound,
            'cost': cost
        })

        samples = OrderedDict(
            py=py
        )

        constants =  [w_tilde, q_c]
        return results, samples, constants
