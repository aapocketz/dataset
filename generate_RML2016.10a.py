#!/usr/bin/env python
from transmitters import transmitters
from source_alphabet import source_alphabet
import analyze_stats
from gnuradio import channels, gr, blocks
import numpy as np
import numpy.fft, cPickle, gzip
import random
from gnuradio import qtgui
import sip
import sys
from PyQt4 import QtGui

'''
Generate dataset with dynamic channel model across range of SNRs
'''

apply_channel = True
plot_constellation = False

dataset = {}

# The output format looks like this
# {('mod type', SNR): np.array(nvecs_per_key, 2, vec_length), etc}

# CIFAR-10 has 6000 samples/class. CIFAR-100 has 600. Somewhere in there seems like right order of magnitude
nvecs_per_key = 200
vec_length = 128
snr_vals = range(-2,20,2) # SNR
sps_vals = [8,12,16] # samples per symbol
ebw_vals = [0.25, 0.50, 0.75] # excess bandwidth (if applicable)

composite_vals = [(alphabet_type, mod_type, snr, sps, ebw)
                  for alphabet_type,trans in transmitters.iteritems() for mod_type in trans for snr in snr_vals for sps in sps_vals for ebw in ebw_vals]

qapp = QtGui.QApplication(sys.argv)
for composite in composite_vals:
    alphabet_type, mod_type, snr, sps, ebw = composite
    dataset[(mod_type.modname, snr, sps, ebw)] = np.zeros([nvecs_per_key, 2, vec_length], dtype=np.float32)
    print composite
    # moar vectors!
    insufficient_modsnr_vectors = True
    modvec_indx = 0
    while insufficient_modsnr_vectors:
        tx_len = int(10e3)
        if mod_type.modname == "QAM16":
            tx_len = int(20e3)
        if mod_type.modname == "QAM64":
            tx_len = int(30e3)
        src = source_alphabet(alphabet_type, tx_len, True)
        mod = mod_type()
        mod.set_parameters(sps, ebw)
        fD = 1
        delays = [0.0, 0.9, 1.7]
        mags = [1, 0.8, 0.3]
        ntaps = 8
        noise_amp = 10**(-snr/10.0) * sps; # need to adjust noise power based on the symbol to noise ratio
        chan = channels.dynamic_channel_model( 200e3, 0.01, 50, .01, 0.5e3, 8, fD, True, 4, delays, mags, ntaps, noise_amp, 0x1337 )

        snk = blocks.vector_sink_c()

        tb = gr.top_block()

        # connect blocks
        if apply_channel:
            tb.connect(src, mod, chan, snk)
        else:
            tb.connect(src, mod, snk)

        if plot_constellation:
            const_snk = qtgui.const_sink_c(10000, "%s %ddB sps=%d ebw=%f" % (mod_type.modname, snr,sps, ebw))
            const_snk.enable_autoscale(True)
            pyobj = sip.wrapinstance(const_snk.pyqwidget(), QtGui.QWidget)
            pyobj.show()
            tb.connect(mod,const_snk)
        tb.start()

        if plot_constellation:
            qapp.exec_()

        tb.wait()


        raw_output_vector = np.array(snk.data(), dtype=np.complex64)
        # start the sampler some random time after channel model transients (arbitrary values here)
        sampler_indx = random.randint(50, 500)
        while sampler_indx + vec_length < len(raw_output_vector) and modvec_indx < nvecs_per_key:
            sampled_vector = raw_output_vector[sampler_indx:sampler_indx+vec_length]

            # normalize to zero mean, unit variance signal
            sampled_vector = sampled_vector - np.mean(sampled_vector)
            sampled_vector = sampled_vector / np.std(sampled_vector)

            dataset[(mod_type.modname, snr, sps, ebw)][modvec_indx,0,:] = np.real(sampled_vector)
            dataset[(mod_type.modname, snr, sps, ebw)][modvec_indx,1,:] = np.imag(sampled_vector)
            # bound the upper end very high so it's likely we get multiple passes through
            # independent channels
            sampler_indx += random.randint(vec_length, round(len(raw_output_vector)*.05))
            modvec_indx += 1

        if modvec_indx == nvecs_per_key:
            # we're all done
            insufficient_modsnr_vectors = False

print "all done. writing to disk"
cPickle.dump( dataset, file("RML2016.10a3_dict.dat", "wb" ) )
