from __future__ import division

import math
import logging
from collections import OrderedDict

import numpy as NP
import scipy.signal

from si import sistr
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
             oversample=1,
             only_positive=True):
    """
    Return the spectrum for the signal *x* calculated via FFT and the
    associated frequencies as a tuple. The *n0* parameter gives the
    index in *x* for time index 0 (*n0* = 0 means that `x[0]` is at
    time 0). The number of spectral samples returned is the next power
    of 2 greater than the length of *x* multiplied by *oversample*. If
    *only_positive*, return the spectrum only for positive frequencies
    (and raise an exception if *x* is not real).
    """
    assert oversample >= 1 and isinstance(oversample, int)
    N = nextpow2(len(x)) * 2**(oversample - 1)
    X = NP.fft.fft(x, n=N) * T_s
    f = NP.fft.fftfreq(N, d=T_s)
    if n0 != 0:
        X *= NP.exp(-1j * 2 * math.pi * NP.arange(N) * n0 / N)
    X = NP.fft.fftshift(X)
    f = NP.fft.fftshift(f)
    if only_positive:
        if any(NP.iscomplex(x)):
            raise ValueError('x is complex and only returning information for positive frequencies --- this is likely not what you want to do')
        X = X[f >= 0]
        f = f[f >= 0]
    return X, f


def blackman_tukey(x,
                   M,
                   L,
                   y=None,
                   window='boxcar',
                   window_args=[],
                   d=1,
                   full=False):
    """
    Compute the Blackman-Tukey cross power spectral density (PSD)
    estimate between the time-domain signals *x* and *y* (must be the
    same length as *x*). If *y* is not given, compute the power
    spectral density estimate of *x*.  Use the spectral window with
    identifier *window* (see the options in
    :func:scipy.`signal.get_window`, e.g., a tuple can be used to pass
    arguments to the window function) and length *M* (i.e., the
    maximum auto-correlation lag to include in the estimate). Compute
    the estimate at *L* uniformly spaced frequency samples where *d*
    is the time domain sample interval. If not *full*, return the
    tuple containing the length *L* PSD estimate and length *L*
    corresponding frequencies. If *full*, also return the estimated
    cross correlation and window function (i.e., a tuple with four
    elements).
    """
    N = len(x)
    assert M <= N
    if y is None:
        y = x
    else:
        assert len(y) == N
    Rxy = scipy.signal.correlate(x, y) / N
    Rxy_window = Rxy[(N - 1) - M:(N - 1) + M + 1]
    window = scipy.signal.get_window(window, 2*M + 1, fftbins=False)
    k_range = NP.arange(0, L)
    shift = NP.exp(2j * NP.pi * k_range * M / L)
    Sxy = NP.fft.fft(window * Rxy_window, n=L) * shift * d
    f = NP.fft.fftfreq(L, d=d)
    if full:
        return (Sxy, f, Rxy, window)
    else:
        return (Sxy, f)


def periodogram(x,
                L,
                y=None,
                d=1,
                full=False):
    """
    Compute the periodogram of the cross power spectral density of *x*
    and *y*. The implementation is based on :func:`blackman-tukey`,
    following the same input and output conventions.
    """
    return blackman_tukey(x, len(x) - 1, L, y=y, d=d, full=full)


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
    # DEPRECATED --- use pyrsss.signal.filter
    assert False
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
        y_out = y[int(M/2):int(M/2) + N]
        if index is not None:
            index_out = index
    elif mode == 'valid':
        D_min = min(N, K)
        D_max = max(N, K)
        y_out = y[(D_min - 1):D_max]
        if index is not None:
            index_out = index[(D_min - int(M/2) - 1):(D_max - int(M/2))]
    elif mode == 'full':
        y_out = y[:L]
        if index is not None:
            delta = index[1] - index[0]
            J = int(M/2)
            index_out = [index[0] - (J-i) * delta for i in range(1, J + 1)] + \
                        index + \
                        [index[-1] + i * delta for i in range(1, J + 1)]
    else:
        raise ValueError('unknown convolution mode {} (choices are same, valid, or full)')
    if index is not None:
        return y_out, index_out
    else:
        return y_out


def differentiator(n, Hz=1):
    """
    Return impulse response for a length *n* filter that approximates
    the differential operator. The sampling frequency is *Hz*.
    """
    return scipy.signal.remez(n,
                              [0, Hz / 2],
                              [1],
                              Hz=Hz,
                              type='differentiator') * Hz * 2 * NP.pi


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
    if verbose:
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
            b1_str = sistr(b1, 'Hz')
            b2_str = sistr(b2, 'Hz')
            stats, medians = band_stats[index]
            if names:
                print('{} ({}): {} -- {}'.format(names[index],
                                                 index,
                                                 b1_str,
                                                 b2_str))
            else:
                print('band {}: {} -- {}'.format(index,
                                                 b1_str,
                                                 b2_str))
            print('abs deviations from {} statistics:'.format(d))
            print('min = {:.3e}  (db={:f})'.format(stats.min,
                                                   20 * math.log10(stats.min)))
            print('med = {:.3e}'.format(medians))
            if d == 1:
                print('std = {:.3e}'.format(stats.sigma))
            print('max = {:.3e} (db={:f})'.format(stats.max,
                                                  20 * math.log10(stats.max)))
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
