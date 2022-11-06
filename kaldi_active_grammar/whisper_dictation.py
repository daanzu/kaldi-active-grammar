# A crude way of using OpenAI Whisper for dictation in KaldiAG.
# This is the RPC client, that sends data to the local whisper RPC server process.
# By Shervin Emami (www.shervinemami.com) 2022
# Based on "alternative_dictation.py" from KaldiAG v1.8, when KaldiAG had some basic support for GCloud dictation.
#
# KaldiAG is (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

# Compatibility between Python2 vs Python3:
from __future__ import print_function   # print function with Python 2/3 compatibility
from __future__ import division

import sys
if sys.version_info[0] == 3:
    # Python3
    from xmlrpc.client import ServerProxy
else:
    # Python2
    from xmlrpclib import ServerProxy
import wave

verbose = False

WHISPER_SERVER_ACCESS = "http://127.0.0.1:8002"     # Where to find our whisper server. Note that Shervin's KaldiAG setup already runs RPC servers on ports 8000 and 8001
whisper_client = ServerProxy(WHISPER_SERVER_ACCESS, allow_none=True)

# Choose what to do if whisper dictation fails (eg: trouble connecting to our local whisper RPC server),
# Some users will want to return "None" so that their Kaldi or other dictation backend will perform the dictation without interrupting the user.
# But some users will want the entire speech engine to close, so that it's obvious when whisper didn't work.
EXIT_IF_WHISPER_FAILED = True


# Create a new process, for the whisper_server to run in the background. It expects "whisper_server.py" to be in the same folder as this Python file.
import subprocess
import os
pardir = os.path.abspath(os.path.join(__file__, os.pardir))
whisper_server = os.path.abspath(os.path.join(pardir, "whisper_server.py"))
subprocess.Popen([sys.executable, whisper_server])



def write_wav(filename, audio_data, sample_rate=16000):
    wf = wave.open(filename, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    wf.writeframes(audio_data)
    wf.close()


def testCUDA():
    print("Test CUDA")

    import torch
    # Making the code device-agnostic
    device_name = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device_name == 'cuda':
        print(f"CUDA version: {torch.version.cuda}")
        print(f"Name of current CUDA device: {torch.cuda.get_device_name(torch.cuda.current_device())}")

    # Creating a test tensor
    x = torch.randint(1, 100, (100, 1000))
    # Checking the device name:
    # Should return 'cpu' by default
    print("Default pytorch device (should be 'CPU'): ", x.device)
    # Transferring tensor to GPU
    x = x.to(torch.device(device_name))
    # Checking the device name:
    # Should return 'cuda:0'
    print("CUDA pytorch device (should be 'cuda:0'): ", x.device)
    # Applying same GPU-accelerated tensor operation
    res_gpu = x ** 2
    res_cpu = res_gpu.cpu()
    print("result: ", res_cpu)



class Whisper(object):

    # Use Whisper to convert the audio data into a text string. If speech_data is not given, will load the audio from a wav file.
    @staticmethod
    def transcribe_data_sync(speech_data=None, model='default', language_code='en-US'):
        # It's possible that calling a GPU-accelerated PyTorch function within the KaldiAG Dragonfly process will cause Dragonfly's
        # calls to xdotool via Text() can have quite long latency on Linux (~200ms instead of ~50ms per call!). So 
        # here (within the Dragonfly process) we will make an RPC interprocess call to our whisper process, that can be GPU-accelerated.

        # For debugging latency of GPU-accelerated PyTorch:
        #testCUDA()
        #return "words"

        try:
            print("Calling the whisper_server RPC server.")
            result = whisper_client.transcribe_using_whisper(speech_data, model, language_code)
            if result:
                return result
        except Exception as e:
            print("Warning: Exception ", e)
            print("Couldn't access the whisper_server at", WHISPER_SERVER_ACCESS, ", is it running?")

        # If we've gotten to this line here, then whisper dictation failed.
        if EXIT_IF_WHISPER_FAILED:
            print("Exiting the speech recognition engine, since whisper failed.")
            os.kill(os.getpid(), 9)
            sys.exit(1)

        return None

