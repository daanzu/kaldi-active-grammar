#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0; see LICENSE.txt file.
#

from __future__ import division, print_function
import collections, itertools, logging, time, threading, wave

from six import binary_type, print_
from six.moves import queue
import sounddevice
import webrtcvad

_log = logging.getLogger("audio")


class MicAudio(object):
    """Streams raw audio from microphone. Data is received in a separate thread, and stored in a buffer, to be read from."""

    FORMAT = 'int16'
    SAMPLE_WIDTH = 2
    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCKS_PER_SECOND = 100
    BLOCK_SIZE_SAMPLES = int(SAMPLE_RATE / float(BLOCKS_PER_SECOND))  # Block size in number of samples
    BLOCK_DURATION_MS = int(1000 * BLOCK_SIZE_SAMPLES // SAMPLE_RATE)  # Block duration in milliseconds

    def __init__(self, callback=None, buffer_s=0, flush_queue=True, start=True, input_device=None, self_threaded=None, reconnect_callback=None):
        self.callback = callback if callback is not None else lambda in_data: self.buffer_queue.put(in_data, block=False)
        self.flush_queue = bool(flush_queue)
        self.input_device = input_device
        self.self_threaded = bool(self_threaded)
        if reconnect_callback is not None and not callable(reconnect_callback):
            _log.error("Invalid reconnect_callback not callable: %r", reconnect_callback)
            reconnect_callback = None
        self.reconnect_callback = reconnect_callback

        self.buffer_queue = queue.Queue(maxsize=(buffer_s * 1000 // self.BLOCK_DURATION_MS))
        self.stream = None
        self.thread = None
        self.thread_cancelled = False
        self.device_info = None
        self._connect(start=start)

    def _connect(self, start=None):
        callback = self.callback
        def proxy_callback(in_data, frame_count, time_info, status):
            callback(bytes(in_data))  # Must copy data from temporary C buffer!

        self.stream = sounddevice.RawInputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype=self.FORMAT,
            blocksize=self.BLOCK_SIZE_SAMPLES,
            # latency=80,
            device=self.input_device,
            callback=proxy_callback if not self.self_threaded else None,
        )

        if self.self_threaded:
            self.thread_cancelled = False
            self.thread = threading.Thread(target=self._reader_thread, args=(callback,))
            self.thread.daemon = True
            self.thread.start()

        if start:
            self.start()

        device_info = sounddevice.query_devices(self.stream.device)
        hostapi_info = sounddevice.query_hostapis(device_info['hostapi'])
        _log.info("streaming audio from '%s' using %s: %i sample_rate, %i block_duration_ms, %i latency_ms",
            device_info['name'], hostapi_info['name'], self.stream.samplerate, self.BLOCK_DURATION_MS, int(self.stream.latency*1000))
        self.device_info = device_info

    def _reader_thread(self, callback):
        while not self.thread_cancelled and self.stream and not self.stream.closed:
            if self.stream.active and self.stream.read_available >= self.stream.blocksize:
                in_data, overflowed = self.stream.read(self.stream.blocksize)
                # print('_reader_thread', read_available, len(in_data), overflowed, self.stream.blocksize)
                if overflowed:
                    _log.warning("audio stream overflow")
                callback(bytes(in_data))  # Must copy data from temporary C buffer!
            else:
                time.sleep(0.001)

    def destroy(self):
        self.stream.close()

    def reconnect(self):
        # FIXME: flapping
        old_device_info = self.device_info
        self.thread_cancelled = True
        if self.thread:
            self.thread.join()
            self.thread = None
        self.stream.close()
        self._connect(start=True)
        if self.reconnect_callback is not None:
            self.reconnect_callback(self)
        if self.device_info != old_device_info:
            raise Exception("Audio reconnect could not reconnect to the same device")

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()

    def read(self, nowait=False):
        """Return a block of audio data. If nowait==False, waits for a block if necessary; else, returns False immediately if no block is available."""
        if self.stream or (self.flush_queue and not self.buffer_queue.empty()):
            if nowait:
                try:
                    return self.buffer_queue.get_nowait()  # Return good block if available
                except queue.Empty as e:
                    return False  # Queue is empty for now
            else:
                return self.buffer_queue.get()  # Wait for a good block and return it
        else:
            return None  # We are done

    def read_loop(self, callback):
        """Block looping reading, repeatedly passing a block of audio data to callback."""
        for block in iter(self):
            callback(block)

    def iter(self, nowait=False):
        """Generator that yields all audio blocks from microphone."""
        while True:
            block = self.read(nowait=nowait)
            if block is None:
                break
            yield block

    def __iter__(self):
        """Generator that yields all audio blocks from microphone."""
        return self.iter()

    def get_wav_length_s(self, data):
        assert isinstance(data, binary_type)
        length_bytes = len(data)
        assert self.FORMAT == 'int16'
        length_samples = length_bytes / self.SAMPLE_WIDTH
        return (float(length_samples) / self.SAMPLE_RATE)

    def write_wav(self, filename, data):
        # _log.debug("write wav %s", filename)
        wf = wave.open(filename, 'wb')
        wf.setnchannels(self.CHANNELS)
        # wf.setsampwidth(self.pa.get_sample_size(FORMAT))
        assert self.FORMAT == 'int16'
        wf.setsampwidth(self.SAMPLE_WIDTH)
        wf.setframerate(self.SAMPLE_RATE)
        wf.writeframes(data)
        wf.close()

    @staticmethod
    def print_list():
        print_("")
        print_("LISTING ALL INPUT DEVICES SUPPORTED BY PORTAUDIO")
        print_("(any device numbers not shown are for output only)")
        print_("")
        devices = sounddevice.query_devices()
        print_(devices)

        # for i in range(0, pa.get_device_count()):
        #     info = pa.get_device_info_by_index(i)

        #     if info['maxInputChannels'] > 0:  # microphone? or just speakers
        #         print_("DEVICE #%d" % info['index'])
        #         print_("    %s" % info['name'])
        #         print_("    input channels = %d, output channels = %d, defaultSampleRate = %d" %
        #             (info['maxInputChannels'], info['maxOutputChannels'], info['defaultSampleRate']))
        #         # print_(info)
        #         try:
        #           supports16k = pa.is_format_supported(16000,  # sample rate
        #               input_device = info['index'],
        #               input_channels = info['maxInputChannels'],
        #               input_format = pyaudio.paInt16)
        #         except ValueError:
        #           print_("    NOTE: 16k sampling not supported, configure pulseaudio to use this device")

        print_("")


class VADAudio(MicAudio):
    """Filter & segment audio with voice activity detection."""

    def __init__(self, aggressiveness=3, **kwargs):
        super(VADAudio, self).__init__(**kwargs)
        self.vad = webrtcvad.Vad(aggressiveness)

    def vad_collector(self, start_window_ms=150, start_padding_ms=100,
        end_window_ms=150, end_padding_ms=None, complex_end_window_ms=None,
        ratio=0.8, blocks=None, nowait=False,
        ):
        """Generator/coroutine that yields series of consecutive audio blocks comprising each phrase, separated by yielding a single None.
            Determines voice activity by ratio of blocks in window_ms. Uses a buffer to include window_ms prior to being triggered.
            Example: (block, ..., block, None, block, ..., block, None, ...)
                      |----phrase-----|        |----phrase-----|
        """
        assert end_padding_ms == None, "end_padding_ms not supported yet"
        num_start_window_blocks = max(1, int(start_window_ms // self.BLOCK_DURATION_MS))
        num_start_padding_blocks = max(0, int((start_padding_ms or 0) // self.BLOCK_DURATION_MS))
        num_end_window_blocks = max(1, int(end_window_ms // self.BLOCK_DURATION_MS))
        num_complex_end_window_blocks = max(1, int((complex_end_window_ms or end_window_ms) // self.BLOCK_DURATION_MS))
        num_end_padding_blocks = max(0, int((end_padding_ms or 0) // self.BLOCK_DURATION_MS))
        _log.debug("%s: vad_collector: num_start_window_blocks=%s num_end_window_blocks=%s num_complex_end_window_blocks=%s",
            self, num_start_window_blocks, num_end_window_blocks, num_complex_end_window_blocks)
        audio_reconnect_threshold_blocks = 5
        audio_reconnect_threshold_time = 50 * self.BLOCK_DURATION_MS / 1000

        ring_buffer = collections.deque(maxlen=max(
            (num_start_window_blocks + num_start_padding_blocks),
            (num_end_window_blocks + num_end_padding_blocks),
            (num_complex_end_window_blocks + num_end_padding_blocks),
        ))
        ring_buffer_recent_slice = lambda num_blocks: itertools.islice(ring_buffer, max(0, (len(ring_buffer) - num_blocks)), None)

        triggered = False
        in_complex_phrase = False
        num_empty_blocks = 0
        last_good_block_time = time.time()

        if blocks is None: blocks = self.iter(nowait=nowait)
        for block in blocks:
            if block is False or block is None:
                # Bad/empty block
                num_empty_blocks += 1
                if (num_empty_blocks >= audio_reconnect_threshold_blocks) and (time.time() - last_good_block_time >= audio_reconnect_threshold_time):
                    _log.warning("%s: no good block received recently, so reconnecting audio", self)
                    self.reconnect()
                    num_empty_blocks = 0
                    last_good_block_time = time.time()
                in_complex_phrase = yield block

            else:
                # Good block
                num_empty_blocks = 0
                last_good_block_time = time.time()
                is_speech = self.vad.is_speech(block, self.SAMPLE_RATE)

                if not triggered:
                    # Between phrases
                    ring_buffer.append((block, is_speech))
                    num_voiced = len([1 for (_, speech) in ring_buffer_recent_slice(num_start_window_blocks) if speech])
                    if num_voiced >= (num_start_window_blocks * ratio):
                        # Start of phrase
                        triggered = True
                        for block, _ in ring_buffer_recent_slice(num_start_padding_blocks + num_start_window_blocks):
                            # print('|' if is_speech else '.', end='')
                            # print('|' if in_complex_phrase else '.', end='')
                            in_complex_phrase = yield block
                        # print('#', end='')
                        ring_buffer.clear()

                else:
                    # Ongoing phrase
                    in_complex_phrase = yield block
                    # print('|' if is_speech else '.', end='')
                    # print('|' if in_complex_phrase else '.', end='')
                    ring_buffer.append((block, is_speech))
                    num_unvoiced = len([1 for (_, speech) in ring_buffer_recent_slice(num_end_window_blocks) if not speech])
                    num_complex_unvoiced = len([1 for (_, speech) in ring_buffer_recent_slice(num_complex_end_window_blocks) if not speech])
                    if (not in_complex_phrase and num_unvoiced >= (num_end_window_blocks * ratio)) or \
                        (in_complex_phrase and num_complex_unvoiced >= (num_complex_end_window_blocks * ratio)):
                        # End of phrase
                        triggered = False
                        in_complex_phrase = yield None
                        # print('*')
                        ring_buffer.clear()

    def debug_print_simple(self):
        print("block_duration_ms=%s" % self.BLOCK_DURATION_MS)
        for block in self.iter(nowait=False):
            is_speech = self.vad.is_speech(block, self.SAMPLE_RATE)
            print('|' if is_speech else '.', end='')

    def debug_loop(self, *args, **kwargs):
        audio_iter = self.vad_collector(*args, **kwargs)
        next(audio_iter)
        while True:
            block = audio_iter.send(False)
