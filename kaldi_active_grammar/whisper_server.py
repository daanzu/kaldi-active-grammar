#!/usr/bin/env python 

# A crude way of using OpenAI Whisper for dictation in KaldiAG.
# This is the Whisper RPC server process.
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
    from xmlrpc.server import SimpleXMLRPCServer
    from xmlrpc.server import SimpleXMLRPCRequestHandler
else:
    # Python2
    from SimpleXMLRPCServer import SimpleXMLRPCServer
    from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler

from datetime import datetime
import subprocess
import time
from threading import Timer
import numpy as np
import tempfile
import os
import io


# Choose between Whisper models: "tiny.en", "base.en", "small.en", "medium.en" or "large".
# If you have a powerful GPU, try "medium.en".
# If you don't have a GPU, stick to "tiny.en" or "base.en".
# TODO: Allow passing the model name from the user
#model_filename = "tiny.en"
model_filename = "medium.en"

# If the audio data is being transferred from Kaldi/Dragonfly to Whisper using a wav file, look for it in the system temp folder.
temp_dir = tempfile.TemporaryDirectory().name
audio_filename = os.path.join(temp_dir,"whisper.wav")

# Whisper allows passing "prompt" that is intended to be the previous sentence or some similar related text, to give a hint
# about what it should expect. This includes formatting, so for example giving a hint of "40's" can push whisper closer to
# decoding the phrase "forties" as "40's" instead of "40s".
# Since I want a lot of commas but not fullstops or capitalising of phrases, I'm using a hint_prompt this way.
# TODO: Allow passing whisper args from the user script.
hint_prompt="oh OK yeah sure, in my 40's I mostly benchmarked a profile of ARM CPU core optimisation"

verbose = False

WHISPER_SERVER_ADDRESS = ("127.0.0.1", 8002)     # Set up our server address. Note that Shervin's KaldiAG setup already runs RPC servers on ports 8000 and 8001


try:
    import whisper
    whisper_imported = True
except ImportError:
    whisper_imported = False
whisper_model = None
whisper_model_started_loading = False


# If you have a BlinkStick USB controlled RGB LED, then set this to True.
ENABLE_BLINKSTICK = True

# BlinkStick USB LED
if ENABLE_BLINKSTICK:
    try:
        from blinkstick import blinkstick
        bstick = blinkstick.find_first()
        if bstick:
            print("Found BlinkStick USB LED", bstick.get_serial())
        else:
            print("Warning: Couldn't access the BlinkStick USB LED")
    except:
        bstick = None

# Show the current mode, using the USB LED.
# args can be 'off', 'on', 'disabled' or 'sleeping'.
def updateLED(args, grammarMode = "Normal"):
    if ENABLE_BLINKSTICK:
        try:
            #print("In updateLED ", args, grammarMode)
            if bstick:
                V = 5  # LED Brightness upto 255
                if args == "on":
                    # Set my BlinkStick LED to green (ON, Normal mode) or blue (ON, Command mode)
                    if grammarMode == "Normal":
                        bstick.set_color(red=0, green=V, blue=0)
                    elif grammarMode == "Yellow":
                        bstick.set_color(red=V, green=V, blue=0)
                    elif grammarMode == "Pink":
                        bstick.set_color(red=V*1.2, green=V/3, blue=V/2.5)
                    elif grammarMode == "BlueGreen":
                        bstick.set_color(red=1, green=9, blue=3)
                    else:
                        bstick.set_color(red=0, green=0, blue=V*1.2)
                elif args == "disabled":
                    # Set my BlinkStick LED to red (disabled)
                    bstick.set_color(red=V*2, green=0, blue=0)
                elif args == "sleeping":
                    # Set my BlinkStick LED to purple (sleeping)
                    bstick.set_color(red=1, green=0, blue=0)
                elif args == "off":
                    # Set my BlinkStick LED to black (off)
                    bstick.set_color(red=0, green=0, blue=0)
        except:
            print("Warning: Couldn't access the BlinkStick USB LED")
            pass


def load_whisper_model():
    global model_filename
    global whisper_model
    global whisper_model_started_loading
    if not whisper_model_started_loading:
        whisper_model_started_loading = True     # Block other RPC threads from loading the model too
        print(datetime.now(), "[Loading whisper pytorch model '" + model_filename + "' during startup. This can take a long time!]")
        updateLED("on", "Pink")
        whisper_model = whisper.load_model(model_filename)
        if whisper_model:
            print(datetime.now(), "[Finished loading whisper model]")
            updateLED("on", "Command")     # Assume that the user is going back to Command-mode after being in Dictation-mode.

        # We should expect the first transciption to be slower than usual, since the GPU must load drivers and ramp up its clocks and perhaps other things.
        # So let's perform a dummy transcription now, to preload everything needed for fast dictation.
        #transcribe_using_whisper(None)
    else:
        # Stall here until the whisper model has been loaded (by another RPC thread running in parallel)
        print(datetime.now(), "[whisper model is already being loaded. Waiting until it is ready]")
        while not whisper_model:
            print(".")
            time.sleep(0.3)   # Sleep 0.3 seconds before trying again

# Give the rest of the speech recognition system a few seconds to do heavy initialisation steps, before we load our heavy whisper model.
Timer(3.0, load_whisper_model).start()



# Decode the audio.
# "decode" will use GreedyDecoder (fast) if beam_size=None, or it will use BeamSearch (slower but more reliable) if beam_size=5 or similar.
# Set fp16=True for RTX GPUs, or False for GTX GPUs. Because GTX & older GPUs are extremely fast at FP32 but terrible at FP16,
# whereas new GPUs such as RTX GPUs are extremely fast at both FP32 and FP16, and in fact slightly faster at FP16.
# Set beam_size=5 if you can handle the slower speed, or use beam_size of 0-3 if you want faster results, but with more chance that whisper
# will get stuck in a repetetive mental loop for a while.
# TODO: Allow passing whisper args from the user script.
options = whisper.DecodingOptions(language="en", fp16=False, prompt=hint_prompt, best_of=None, beam_size=3, temperature=0.0, patience=1.3)


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


# Use Whisper to convert the audio data into a text string. If speech_data is not given, will load the audio from a wav file.
def transcribe_using_whisper(speech_data=None, model='default', language_code='en-US'):
    transcript = "Unknown"
    # Wrap our code in a big try/exception block, to make debugging RPCs more clear.
    try:

        # For debugging latency of GPU-accelerated PyTorch:
        #testCUDA()
        #return "words"

        if not whisper_imported:
            _log.error("Cannot find one of the Whisper packages!")
            return None

        # Allow to lazily load the model upon first actual use, so that startup is fast for times when we just want command-mode, not whisper dictation.
        global whisper_model
        if not whisper_model:
            load_whisper_model()

        updateLED("on", "Normal")
        start_inference = time.perf_counter()

        # Load the audio data.
        # Whisper is much faster when using 'model.decode' instead of 'model.transcribe'. See "https://github.com/openai/whisper/discussions/391"
        # So instead of simply calling transcribe(filename), we will load the audio, pad it to 30 seconds, generate the log-mel spectogram, copy the data to GPU, then decode the audio.
        audio = None
        try:
            #result = whisper_model.transcribe(audio_filename, language='english')
            if speech_data:
                audio = np.frombuffer(speech_data.data, np.int16).flatten().astype(np.float32) / 32768.0
            else:
                audio = whisper.load_audio(audio_filename)
        except Exception as e:
            print(datetime.now(), "[Exception!:", e, "]")
            audio = None

        if not isinstance(audio, np.ndarray):
            # We couldn't load the audio file, so use an empty buffer of silence.
            audio = np.zeros((10000), np.float32)

        # Whisper only works on 30 second audio segments.
        audio = whisper.pad_or_trim(audio)

        # Make log-mel spectrogram and move it to the same device as the model (GPU)
        mel = whisper.log_mel_spectrogram(audio).to(whisper_model.device)

        # Decode the audio.
        result = whisper.decode(whisper_model, mel, options)
        if result:
            transcript = result.text

        elapsed_inference = time.perf_counter() - start_inference

        print(datetime.now(), u"[According to OpenAI Whisper after {}s, you said: {}".format(elapsed_inference, transcript))
        if verbose:
            print(datetime.now(), "[", result, "]")
        updateLED("on", "Command")     # Assume that the user is going back to Command-mode after being in Dictation-mode.
    except Exception as e:
        print(datetime.now(), "[Exception raised: ", e, "]")
        return None
        
    return transcript



# Restrict XMLRPC server to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

def setup_xmlrpc_server():
    server_quit = 0
    print(datetime.now(), "[Setting up the whisper_server XMLRPC server at", WHISPER_SERVER_ADDRESS, "]")
    whisperServer = SimpleXMLRPCServer(WHISPER_SERVER_ADDRESS, requestHandler=RequestHandler, allow_none=True)
    whisperServer.register_function(xmlrpc_kill, "kill")
    whisperServer.register_function(transcribe_using_whisper, "transcribe_using_whisper")
    #TODO: Disable this for security when not debugging:
    #whisperServer.register_introspection_functions()
    return whisperServer


def xmlrpc_kill():
    print(datetime.now(), "[XMLRPC whisper_server received kill event]")
    after(2, die)

def die():
    print(datetime.now(), "[Closing the whisper_server]")
    server_quit = 1
    temp_dir.cleanup()      # Remove the tmp audio file that we created.
    os.kill(os.getpid(), 9)
    sys.exit()


def whisper_server_main(args):
    print(datetime.now(), "[whisper_server process has started]")

    whisperServer = setup_xmlrpc_server()

    # Get the XMLRPC server to start in the background quite soon
    server_quit = 0
    def start_server():
        while not server_quit:
            whisperServer._handle_request_noblock()
            #print(".")  # Show that another request has been handled.

    Timer(0.3, start_server).start()

    print(datetime.now(), "[whisper_server is ready]")

    # Run forever ...


if __name__ == "__main__":
    #print(datetime.now(), "[whisper_server is in __main__()]")
    whisper_server_main(sys.argv[1:])
    #print(datetime.now(), "[whisper_server is ending __main__()]")

#print(datetime.now(), "[whisper_server is at end of script.]")

