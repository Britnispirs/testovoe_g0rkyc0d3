class VoiceAssistantSpeech {
  constructor() {
    this.recognition = null;
    this.isListening = false;
    this.isTtsEnabled = localStorage.getItem('tts_enabled') !== 'false';
    this.recognitionSupported = 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;

    this.canvas = null;
    this.canvasCtx = null;
    this.audioCtx = null;
    this.analyser = null;
    this.audioSource = null;
    this.mediaStream = null;
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.dataArray = null;
    this.visualizerAnimationId = null;
    this.isMicActive = false;

    this.onResultCallback = null;
    this.onErrorCallback = null;
    this.onStatusChangeCallback = null;

    this.webSpeechResult = '';
    this._initRecognition();
  }

  _initRecognition() {
    if (!this.recognitionSupported) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.recognition = new SpeechRecognition();
    this.recognition.lang = 'ru-RU';
    this.recognition.continuous = false;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;

    this.recognition.onstart = () => {
      this.isListening = true;
      this.webSpeechResult = '';
      if (this.onStatusChangeCallback) {
        this.onStatusChangeCallback('listening');
      }
    };

    this.recognition.onresult = (event) => {
      let interim = '';
      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }

      const activeText = finalTranscript || interim;
      if (finalTranscript) {
        this.webSpeechResult = finalTranscript.trim();
      }
      if (this.onResultCallback && activeText) {
        this.onResultCallback(activeText, false);
      }
    };

    this.recognition.onerror = (event) => {
      console.warn('Web Speech API error:', event.error);
      if (!this.mediaRecorder) {
        this.isListening = false;
        if (this.onErrorCallback) {
          this.onErrorCallback(event.error);
        }
        if (this.onStatusChangeCallback) {
          this.onStatusChangeCallback('idle');
        }
        this.stopMicStream();
      }
    };

    this.recognition.onend = () => {
      if (this.isListening && !this.mediaRecorder) {
        this.isListening = false;
        if (this.onResultCallback && this.webSpeechResult) {
          this.onResultCallback(this.webSpeechResult, true);
        }
        if (this.onStatusChangeCallback) {
          this.onStatusChangeCallback('idle');
        }
        this.stopMicStream();
      }
    };
  }

  setCallbacks({ onResult, onError, onStatusChange }) {
    this.onResultCallback = onResult;
    this.onErrorCallback = onError;
    this.onStatusChangeCallback = onStatusChange;
  }

  async startListening() {
    if (this.isListening) return;

    try {
      this.cancelSpeech();
      this.webSpeechResult = '';
      this.audioChunks = [];
      await this.startMicStream();

      if (window.MediaRecorder && this.mediaStream) {
        try {
          const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/ogg');
          
          this.mediaRecorder = new MediaRecorder(this.mediaStream, { mimeType });
          this.mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
              this.audioChunks.push(e.data);
            }
          };
          this.mediaRecorder.onstop = async () => {
            await this._handleRecordedAudio();
          };
          this.mediaRecorder.start(100);
        } catch (recErr) {
          console.warn('Could not start MediaRecorder:', recErr);
          this.mediaRecorder = null;
        }
      }

      this.isListening = true;
      if (this.onStatusChangeCallback) {
        this.onStatusChangeCallback('listening');
      }

      if (this.recognition) {
        try {
          this.recognition.start();
        } catch (e) {
          console.warn('SpeechRecognition start failed:', e);
        }
      }
    } catch (e) {
      this.isListening = false;
      this.stopMicStream();
      if (this.onErrorCallback) this.onErrorCallback(e.message || 'mic_error');
    }
  }

  stopListening() {
    if (!this.isListening) return;
    this.isListening = false;

    if (this.onStatusChangeCallback) {
      this.onStatusChangeCallback('processing');
    }

    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (e) {}
    }

    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      try {
        this.mediaRecorder.stop();
      } catch (e) {}
    } else {
      this.stopMicStream();
      if (this.webSpeechResult && this.onResultCallback) {
        this.onResultCallback(this.webSpeechResult, true);
      }
      if (this.onStatusChangeCallback) {
        this.onStatusChangeCallback('idle');
      }
    }
  }

  async _handleRecordedAudio() {
    this.stopMicStream();

    if (this.audioChunks.length === 0) {
      if (this.webSpeechResult && this.onResultCallback) {
        this.onResultCallback(this.webSpeechResult, true);
      }
      if (this.onStatusChangeCallback) this.onStatusChangeCallback('idle');
      return;
    }

    const mimeType = (this.mediaRecorder && this.mediaRecorder.mimeType) || 'audio/webm';
    const audioBlob = new Blob(this.audioChunks, { type: mimeType });
    this.mediaRecorder = null;
    this.audioChunks = [];

    if (audioBlob.size < 500) {
      if (this.webSpeechResult && this.onResultCallback) {
        this.onResultCallback(this.webSpeechResult, true);
      }
      if (this.onStatusChangeCallback) this.onStatusChangeCallback('idle');
      return;
    }

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'speech.webm');
      formData.append('language', 'ru');

      const response = await fetch('/api/voice/transcribe', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        const recognized = (data.text || '').trim();
        if (recognized) {
          if (this.onResultCallback) {
            this.onResultCallback(recognized, true);
          }
          if (this.onStatusChangeCallback) this.onStatusChangeCallback('idle');
          return;
        }
      }
    } catch (err) {
      console.warn('Backend STT failed, falling back to Web Speech result:', err);
    }

    if (this.webSpeechResult && this.onResultCallback) {
      this.onResultCallback(this.webSpeechResult, true);
    }
    if (this.onStatusChangeCallback) {
      this.onStatusChangeCallback('idle');
    }
  }

  async transcribeAudioFile(file) {
    if (!file) return null;
    const formData = new FormData();
    formData.append('audio', file, file.name);
    formData.append('language', 'ru');

    try {
      if (this.onStatusChangeCallback) this.onStatusChangeCallback('processing');
      const response = await fetch('/api/voice/transcribe', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        return data.text || '';
      }
    } catch (err) {
      console.error('Audio file transcription failed:', err);
    } finally {
      if (this.onStatusChangeCallback) this.onStatusChangeCallback('idle');
    }
    return null;
  }

  toggleListening() {
    if (this.isListening) {
      this.stopListening();
    } else {
      this.startListening();
    }
  }

  toggleTts() {
    this.isTtsEnabled = !this.isTtsEnabled;
    localStorage.setItem('tts_enabled', this.isTtsEnabled ? 'true' : 'false');
    if (!this.isTtsEnabled) {
      this.cancelSpeech();
    }
    return this.isTtsEnabled;
  }

  speak(text) {
    if (!this.isTtsEnabled || !('speechSynthesis' in window)) return;
    if (!text) return;

    this.cancelSpeech();

    const cleanText = text
      .replace(/•/g, '')
      .replace(/[#*_~`]/g, '')
      .replace(/«|»/g, '')
      .trim();

    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'ru-RU';
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    const voices = window.speechSynthesis.getVoices();
    const ruVoice = voices.find(v => v.lang.startsWith('ru') && !v.name.includes('eSpeak')) ||
                    voices.find(v => v.lang.startsWith('ru'));
    if (ruVoice) {
      utterance.voice = ruVoice;
    }

    utterance.onstart = () => {
      if (this.onStatusChangeCallback) this.onStatusChangeCallback('speaking');
    };

    utterance.onend = () => {
      if (this.onStatusChangeCallback && !this.isListening) {
        this.onStatusChangeCallback('idle');
      }
    };

    utterance.onerror = () => {
      if (this.onStatusChangeCallback && !this.isListening) {
        this.onStatusChangeCallback('idle');
      }
    };

    window.speechSynthesis.speak(utterance);
  }

  cancelSpeech() {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }

  initVisualizer(canvasElement) {
    this.canvas = canvasElement;
    this.canvasCtx = canvasElement.getContext('2d');
    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());
    this._startVisualizerLoop();
  }

  resizeCanvas() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = rect.width * (window.devicePixelRatio || 1);
    this.canvas.height = rect.height * (window.devicePixelRatio || 1);
  }

  async startMicStream() {
    try {
      if (!this.audioCtx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        this.audioCtx = new AudioCtx();
      }
      if (this.audioCtx.state === 'suspended') {
        await this.audioCtx.resume();
      }

      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 64;
      this.audioSource = this.audioCtx.createMediaStreamSource(this.mediaStream);
      this.audioSource.connect(this.analyser);
      this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
      this.isMicActive = true;
    } catch (err) {
      this.isMicActive = false;
      throw err;
    }
  }

  stopMicStream() {
    this.isMicActive = false;
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }
    if (this.audioSource) {
      try { this.audioSource.disconnect(); } catch (e) {}
      this.audioSource = null;
    }
  }

  _startVisualizerLoop() {
    let phase = 0;

    const render = () => {
      this.visualizerAnimationId = requestAnimationFrame(render);
      if (!this.canvas || !this.canvasCtx) return;

      const ctx = this.canvasCtx;
      const width = this.canvas.width;
      const height = this.canvas.height;
      const centerY = height / 2;

      ctx.clearRect(0, 0, width, height);

      let intensity = 0;
      if (this.isMicActive && this.analyser && this.dataArray) {
        this.analyser.getByteFrequencyData(this.dataArray);
        let sum = 0;
        for (let i = 0; i < this.dataArray.length; i++) {
          sum += this.dataArray[i];
        }
        intensity = (sum / this.dataArray.length) / 255;
      }

      const numBars = 28;
      const barSpacing = width / numBars;
      const barWidth = Math.max(2.5, barSpacing * 0.45);

      for (let i = 0; i < numBars; i++) {
        const x = i * barSpacing + barSpacing / 2;
        let barHeight = 4;

        if (this.isMicActive) {
          const freqIndex = Math.floor((i / numBars) * (this.dataArray ? this.dataArray.length : 1));
          const freqVal = this.dataArray ? this.dataArray[freqIndex] / 255 : 0;
          const wave = Math.sin(phase + i * 0.3) * 0.5 + 0.5;
          barHeight = 4 + (freqVal * 0.7 + wave * 0.3) * (height * 0.8) * Math.max(0.4, intensity * 2);
        } else {
          barHeight = 4 + Math.sin(phase * 0.5 + i * 0.2) * 2;
        }

        const gradient = ctx.createLinearGradient(0, centerY - barHeight / 2, 0, centerY + barHeight / 2);
        if (this.isMicActive) {
          gradient.addColorStop(0, '#818cf8');
          gradient.addColorStop(0.5, '#6366f1');
          gradient.addColorStop(1, '#4f46e5');
        } else {
          gradient.addColorStop(0, 'rgba(148, 163, 184, 0.2)');
          gradient.addColorStop(1, 'rgba(148, 163, 184, 0.1)');
        }

        ctx.fillStyle = gradient;
        ctx.beginPath();
        const top = centerY - barHeight / 2;
        const radius = barWidth / 2;

        if (ctx.roundRect) {
          ctx.roundRect(x - barWidth / 2, top, barWidth, barHeight, radius);
        } else {
          ctx.rect(x - barWidth / 2, top, barWidth, barHeight);
        }
        ctx.fill();
      }

      phase += this.isMicActive ? 0.15 : 0.03;
    };

    render();
  }
}
