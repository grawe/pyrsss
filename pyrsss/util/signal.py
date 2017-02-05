from __future__ import division

import math
import logging
from collections import OrderedDict

import numpy as NP

from ..stats.stats import Stats

logger = logging.getLogger('pyrsss.util.signal')


def rect(t, a):
    """
    ???
    """
    x = NP.zeros_like(t)
    x[NP.abs(t) < a/2] = 1
    x[NP.abs(t) == a/2] = 1/2
    return x


def nextpow2(N):
    """
    Return the power of 2 greater than or equal to *N*.
    """
    return 2**int(math.ceil(math.log(N, 2)))


def spectrum(x,
             n0=0,
             T_s=1,
             oversample=1):
    """
    ???
    """
    N = nextpow2(len(x)) * oversample
    X = NP.fft.fft(x, n=N) * T_s
    f = NP.fft.fftfreq(N, d=T_s)
    if n0 != 0:
        X *= NP.exp(-1j * 2 * math.pi * NP.arange(N) * (n0 + (N - len(x))) / N)
        #print(NP.exp(-1j * 2 * math.pi * NP.arange(N) * (n0 + (N - len(x))) / N))
        # HACK
        X[f < 0] *= -1
    return (NP.fft.fftshift(X),
            NP.fft.fftshift(f))


# def convolve(x, y, T_s=1):
#     """
#     ???
#     """
#     N_x = len(x)
#     N_y = len(y)
#     # compute the power next largest power of 2
#     N2_x = int(math.ceil(math.log(N_x, 2)))
#     N2_y = int(math.ceil(math.log(N_y, 2)))
#     N2 = max(N2_x, N2_y)
#     # compute FFTs
#     X = NP.fft.fft(x, n=N2)
#     Y = NP.fft.fft(y, n=N2)



def lp_fir_type(h):
    """
    Determine if FIR filter impulse response *h* is symmetric or
    antisymmetric. Return {1, 2, 3, 4} depending on FIR filter type or
    None if the FIR filter is not linear phase.
    """
    M = len(h) - 1
    n_range = range(M + 1)
    if M % 2 == 0:
        if all([NP.isclose(h[n], h[M - n]) for n in n_range]):
            return 1
        elif all([NP.isclose(h[n], -h[M - n]) for n in n_range]):
            return 3
        else:
            return None
    else:
        if all([NP.isclose(h[n], h[M - n]) for n in n_range]):
            return 2
        elif all([NP.isclose(h[n], -h[M - n]) for n in n_range]):
            return 4
        else:
            return None
    assert False


def lp_fir_filter(h, x, real=True, mode='same', index=None):
    """
    Apply a linear phase FIR filter with impulse response *h* to the
    signal *x* and return the output (with same length as *x*) after
    compensating for the constant group delay. If *real*, return only
    the real part of the filter output.

    The *mode* parameter specifies the portion of the convolution
    returned. If `same` the output will be the same shape as *x*. If
    `full` the entire convolution is returned (`len(h) + len(x) -
    1`). Finally if mode is 'valid', return only that portion for
    which *h* and *x* completely overlap (i.e., the portion where no 0
    boundary values are included).

    If *index* is provided, return the slice of *index* corresponding
    to *mode*. The purpose is to associate the correct time indices
    with the filter output.
    """
    lp_type = lp_fir_type(h)
    if lp_type is None:
        raise ValueError('FIR filter is not linear phase')
    if lp_type in [2, 4]:
        logger.warning('linear phase FIR filter is type {} --- cannot compensate for half sample delay (compensating for integer portion only)')
    N = len(x)
    K = len(h)
    L = N + K - 1
    L_fft = nextpow2(L)
    H = NP.fft.fft(h, n=L_fft)
    X = NP.fft.fft(x, n=L_fft)
    y = NP.fft.ifft(H * X)
    if real:
        y = NP.real(y)
    M = len(h) - 1
    if mode == 'same':
        y_out = y[int(M/2):int(M/2) + len(x)]
        if index:
            index_out = index[int(M/2):int(M/2) + len(x)]
    elif mode == 'valid':
        D_min = min(N, K)
        D_max = max(N, K)
        y_out = y[(D_min - 1):D_max]
        if index:
            index_out = index[(D_min - 1):D_max]
    elif mode == 'full':
        y_out = y
        index_out = index
    else:
        raise ValueError('unknown convolution mode {} (choices are same, valid, or full)')
    if index:
        return y_out, index_out
    else:
        return y_out


def fir_response(h, bands, desired, Hz=1, names=None, verbose=True):
    """
    Report on the frequency response magnitude characteristics of the
    filter with impulse response *h*. The list-like *bands* is twice
    the length of *desired*, i.e., one filter desired magnitude per
    two value frequency band specification, see
    :func:`scipy.signal.remez`). The parameter *Hz* is the sample rate
    and *names*, if given, associates a string name with each
    band. Return a mapping from band identifiers to absolute desired
    to filter magnitude per band :class:`Stats` and the median
    value. If *vervose*, dump a report to stdout.
    """
    # check for argument consistency
    bands = NP.array(bands)
    if len(bands) % 2 != 0:
        raise ValueError('# of band boundaries must be even')
    if len(bands) / 2 != len(desired):
        raise ValueError('# of band boundaries must equal to twice the length of desired (i.e., 2 boundaries per band and 1 desired amplitude per band)')
    if any(bands < 0):
        raise ValueError('no value of bands may be negative')
    if any(bands > Hz / 2):
        raise ValueError('no value of bands may be larger than the Nyquist rate (Hz / 2)')
    if names:
        if len(names) != len(desired):
            raise ValueError('there should be an equal number of bands as names')
    # compute filter frequency response
    L = nextpow2(10 * len(h))
    H = NP.fft.rfft(h, n=L)
    f = NP.fft.rfftfreq(L, 1/Hz)
    # gather stats per band
    band_stats = OrderedDict()
    medians = OrderedDict()
    band_tuples = zip(bands[::2], bands[1::2])
    for index, ((b1, b2), d) in enumerate(zip(band_tuples, desired)):
        I = [i for  i, f_i in enumerate(f) if b1 <= f_i < b2]
        diff = d - NP.abs([H[i] for i in I])
        band_stats[index] = Stats(*NP.abs(diff)), NP.median(diff)
        if names:
            band_stats[names[index]] = band_stats[index]
    if vervose:
        # report on linear phase determined from symmetry of h
        fir_type = lp_fir_type(h)
        if fir_type:
            print('FIR filter is linear phase type {}'.format(fir_type))
        else:
            print('FIR filter is NOT linear phase')
        print('')
        # output report
        for index, d in enumerate(desired):
            b1, b2 = band_tuples[index]
            stats, medians = band_stats[index]
            if names:
                print('{} ({}) abs deviations from {}:'.format(names[index], index, d))
            else:
                print('band {} abs deviations from {}:'.format(index, d))
            print('min = {:.3e}  (db={:f})'.format(stats.min,
                                                   20 * math.log10(stats.min)))
            print('med = {:.3e}'.format(medians))
            if d == 1:
                print('std = {:.3e}'.format(stats.sigma))
            print('max = {:.3e} (db={:f}'.format(stats.max,
                                                 20 * math.log10(stats.max)))
            print('')
    return band_stats


if __name__ == '__main__':
    import pylab as PL

    # Test 1: Plot spectrum of sinusoid
    phi = 0  # phase offset [radians]
    f0  = 5  # frequency [Hz]
    A   = 1  # amplitude

    T_max = 1   # time max (time range from -T_max to T_max) [s]
    T_s = 1e-2  # sampling frequency [s]

    t = NP.arange(-T_max,
                  T_max + T_s / 2,
                  T_s)

    assert len(t) % 2 == 1 # even case not implemented
    n0 = (len(t) - 1) / 2

    x = NP.sin(2 * math.pi * f0 * t + phi)

    X, f = spectrum(x, n0=n0, T_s=T_s, oversample=4)

    fig = PL.figure()
    PL.subplot(211)
    PL.scatter(t, x, edgecolors='None')
    PL.xlim(-T_max, T_max)
    PL.xlabel('Time [s]')
    PL.subplot(212)
    PL.plot(f, NP.abs(X), label='DFT')
    PL.axvline(f0, c='r', label='FT')
    PL.axvline(-f0, c='r')
    PL.xlim(-2 * f0, 2 * f0)
    PL.legend()
    PL.xlabel('Frequency [Hz]')
    PL.suptitle('Sinusoid Example')

    # Test 3: Plot spectrum of rect
    a = 1  # width of rect function

    # T_max = 1   # time max (time range from -T_max to T_max) [s]
    T_max = 10   # time max (time range from -T_max to T_max) [s]
    #T_s = 1e-2  # sampling frequency (instead, calculate given a)
    T_s = 1e-2  # sampling frequency (instead, calculate given a)

    t = NP.arange(-T_max,
                  T_max + T_s / 2,
                  T_s)
    assert len(t) % 2 == 1 # even case not implemented
    n0 = (len(t) - 1) / 2
    # n0 = len(t) / 2
    # BUT: n0 = len(t) / 2 results in 0 imaginary part

    x = rect(t, a)

    X, f = spectrum(x, n0=n0, T_s=T_s, oversample=4)

    print(NP.linalg.norm(NP.imag(X)))

    N_FT = 4 * len(f)
    f_FT = NP.linspace(f[0], f[-1], N_FT)
    X_FT = abs(a) * NP.sinc(f_FT * a)

    fig = PL.figure()
    PL.subplot(211)
    PL.stem(t, x)
    PL.xlim(-T_max, T_max)
    PL.xlabel('Time [s]')
    PL.subplot(212)
    PL.plot(f, NP.real(X), label='DFT')
    PL.plot(f_FT, X_FT, label='FT', color='r')

    PL.suptitle('Rect Example')

    PL.show()