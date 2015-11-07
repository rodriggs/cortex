"""
Optimization routines.
"""
import ipdb
import numpy as np
import theano
from theano import tensor as T
import tools
from collections import OrderedDict


profile = False

# optimizers
# name(hyperp, tparams, grads, inputs (list), cost) = f_grad_shared, f_update
def adam(lr, tparams, grads, inp, cost, extra_ups=[], extra_outs=[], exclude_params=set([])):
    gshared = [theano.shared(p.get_value() * 0., name='%s_grad'%k) for k, p in tparams.iteritems()]

    g_norm = 0.

    for i in xrange(len(grads)):

        grads[i] /= T.cast(100, dtype=theano.config.floatX)
        g_norm += (grads[i]**2).sum()

    g_norm = T.sqrt(g_norm)
    scaler = 5 / T.maximum(5, g_norm)

    for i in xrange(len(grads)):
        grads[i] *= scaler

    gsup = [(gs, g) for gs, g in zip(gshared, grads)]

    f_grad_shared = theano.function(inp, [cost]+extra_outs, updates=gsup+extra_ups, profile=profile)

    lr0 = 0.0002
    b1 = 0.1
    b2 = 0.001
    e = 1e-8

    updates = OrderedDict()

    i = theano.shared(np.float32(0.))
    i_t = i + 1.
    fix1 = 1. - b1**(i_t)
    fix2 = 1. - b2**(i_t)
    lr_t = lr0 * (T.sqrt(fix2) / fix1)

    for p, g in zip(tparams.values(), gshared):
        m = theano.shared(p.get_value() * 0.)
        v = theano.shared(p.get_value() * 0.)
        m_t = (b1 * g) + ((1. - b1) * m)
        v_t = (b2 * T.sqr(g)) + ((1. - b2) * v)
        g_t = m_t / (T.sqrt(v_t) + e)
        p_t = p - (lr_t * g_t)
        updates[m] =  m_t
        updates[v] =  v_t
        if p.name not in exclude_params:
            updates[p] = p_t

    for k, updated_param in updates.items():
        if 'W' in str(k):
            col_norms = T.sqrt(T.sqr(updated_param).sum(axis=0))
            desired_norms = T.clip(col_norms, 0, 1.9365)
            ratio = (desired_norms / (1e-7 + col_norms))
            updates[k] = updated_param * ratio

    updates[i] = i_t

    f_update = theano.function([lr], [], updates=updates,
                               on_unused_input='ignore', profile=profile)

    return f_grad_shared, f_update

def adadelta(lr, tparams, grads, inp, cost, extra_ups=[], extra_outs=[], exclude_params=set([])):
    zipped_grads = [theano.shared(p.get_value() * np.float32(0.), name='%s_grad'%k) for k, p in tparams.iteritems()]
    running_up2 = [theano.shared(p.get_value() * np.float32(0.), name='%s_rup2'%k) for k, p in tparams.iteritems()]
    running_grads2 = [theano.shared(p.get_value() * np.float32(0.), name='%s_rgrad2'%k) for k, p in tparams.iteritems()]

    zgup = [(zg, g) for zg, g in zip(zipped_grads, grads)]
    rg2up = [(rg2, 0.95 * rg2 + 0.05 * (g ** 2)) for rg2, g in zip(running_grads2, grads)]

    f_grad_shared = theano.function(inp, [cost]+extra_outs, updates=zgup+rg2up+extra_ups, profile=profile)

    updir = [-T.sqrt(ru2 + 1e-6) / T.sqrt(rg2 + 1e-6) * zg for zg, ru2, rg2 in zip(zipped_grads, running_up2, running_grads2)]
    ru2up = [(ru2, 0.95 * ru2 + 0.05 * (ud ** 2)) for ru2, ud in zip(running_up2, updir)]
    param_up = [(p, p + ud) for p, ud in zip(tools.itemlist(tparams), updir) if p.name not in exclude_params]

    f_update = theano.function([lr], [], updates=ru2up+param_up, on_unused_input='ignore', profile=profile)

    return f_grad_shared, f_update

def rmsprop(lr, tparams, grads, inp, cost, extra_ups=[], extra_outs=[], exclude_params=set([])):
    zipped_grads = [theano.shared(p.get_value() * np.float32(0.), name='%s_grad'%k) for k, p in tparams.iteritems()]
    running_grads = [theano.shared(p.get_value() * np.float32(0.), name='%s_rgrad'%k) for k, p in tparams.iteritems()]
    running_grads2 = [theano.shared(p.get_value() * np.float32(0.), name='%s_rgrad2'%k) for k, p in tparams.iteritems()]

    zgup = [(zg, g) for zg, g in zip(zipped_grads, grads)]
    rgup = [(rg, 0.95 * rg + 0.05 * g) for rg, g in zip(running_grads, grads)]
    rg2up = [(rg2, 0.95 * rg2 + 0.05 * (g ** 2)) for rg2, g in zip(running_grads2, grads)]

    f_grad_shared = theano.function(inp, [cost]+extra_outs, updates=zgup+rgup+rg2up+extra_ups, profile=profile)

    updir = [theano.shared(p.get_value() * np.float32(0.), name='%s_updir'%k) for k, p in tparams.iteritems()]
    updir_new = [(ud, 0.9 * ud - 1e-4 * zg / T.sqrt(rg2 - rg ** 2 + 1e-4)) for ud, zg, rg, rg2 in zip(updir, zipped_grads, running_grads, running_grads2)]
    param_up = [(p, p + udn[1]) for p, udn in zip(tools.itemlist(tparams), updir_new) if p.name not in exclude_params]
    f_update = theano.function([lr], [], updates=updir_new+param_up, on_unused_input='ignore', profile=profile)

    return f_grad_shared, f_update

def sgd(lr, tparams, grads, inp, cost, extra_ups=[], extra_outs=[], exclude_params=set([])):
    gshared = [theano.shared(p.get_value() * 0., name='%s_grad'%k) for k, p in tparams.iteritems()]

    gsup = [(gs, g) for gs, g in zip(gshared, grads)]

    f_grad_shared = theano.function(inp, [cost]+extra_outs, updates=gsup+extra_ups, profile=profile)

    pup = [(p, p - lr * g) for p, g in zip(tools.itemlist(tparams), gshared) if p.name not in exclude_params]
    f_update = theano.function([lr], [], updates=pup, profile=profile)

    return f_grad_shared, f_update
