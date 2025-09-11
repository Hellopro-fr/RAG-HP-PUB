(function ($) {
    $.fn.transcription = function (options) {
        const defaults = {
            url: "ws://172.18.6.40:8765/ws/google/transcription",
            elements: {
                start: null,
                stop: null,
            },
            onTranscript: function (data) { },
            onStatusChange: function (status) { },
            onError: function (error) { },
            onAudioComplete: function (blob) { },
            onDrawVisualizeCallback: function (stream, audioContext) { },
            config: {
                sampleRate: 16000,
                languageCode: "fr-FR",
            },
        };

        const settings = $.extend({}, defaults, options);

        return this.each(function () {
            const $this = $(this);
            let streamer = null;

            const transcription = {
                socket: null,
                audioContext: null,
                mediaStream: null,
                processor: null,
                analyser: null,
                isRecording: false,
                reconnectAttempts: 0,
                maxReconnectAttempts: 5,
                reconnectTimeout: null,
                visualizationFrameId: null,
                pendingAudioProcessing: false,
                shutdownCallback: null,
                mediaRecorder: null,
                audioChunks: [],
                options: {},

                init: function () {
                    this.bindButtons();
                    streamer = this;

                    $(window).on("beforeunload", async () => await streamer.stop());
                },

                bindButtons: () => {
                    if (settings.elements.start) {
                        $(settings.elements.start).on("click", async () => {
                            try {
                                await streamer.start();
                            } catch (e) {
                                settings.onError(e);
                            }
                        });
                    }

                    if (settings.elements.stop) {
                        $(settings.elements.stop).on("click", async () => {
                            try {
                                await streamer.stop();
                                settings.onStatusChange("disconnected");
                            } catch (e) {
                                settings.onError(e);
                                settings.onStatusChange("disconnected");
                            }
                        });
                    }
                },

                async start() {
                    if (this.isRecording) return;

                    console.info("Connection established");
                    try {
                        await this.initializeAudioContext();
                        await this.initializeWebSocket();
                        this.isRecording = true;
                    } catch (error) {
                        settings.onError(error);
                        throw error;
                    }
                },

                async initializeAudioContext() {
                    // Vérification pour les anciens navigateurs
                    navigator.getUserMedia = navigator.getUserMedia ||
                        navigator.webkitGetUserMedia ||
                        navigator.mozGetUserMedia;

                    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                        if (!navigator.getUserMedia) {
                            const errorMsg = "L'API getUserMedia n'est pas supportée par ce navigateur.";
                            settings.onError(new Error(errorMsg));
                            throw new Error(errorMsg);
                        }
                        // Utilise l'ancienne API basée sur les callbacks en la "promisifiant"
                        this.mediaStream = await new Promise((resolve, reject) => {
                            navigator.getUserMedia({ audio: true }, resolve, reject);
                        });
                    } else {
                        // Utilise l'API moderne basée sur les Promises
                        this.mediaStream = await navigator.mediaDevices.getUserMedia({
                            audio: {
                                channelCount: 1,
                                sampleRate: settings.config.sampleRate,
                            },
                        });
                    }

                    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();

                    this.mediaRecorder = new MediaRecorder(this.mediaStream);
                    this.mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            this.audioChunks.push(event.data);
                        }
                    };
                    this.mediaRecorder.start();

                    const source = this.audioContext.createMediaStreamSource(this.mediaStream);
                    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
                    this.processor.onaudioprocess = this.handleAudioProcess.bind(this);
                    source.connect(this.processor);
                    this.processor.connect(this.audioContext.destination);

                    settings.onDrawVisualizeCallback(this.mediaStream, this.audioContext);
                },

                async initializeWebSocket() {
                    this.socket = new WebSocket(settings.url);

                    this.socket.onopen = () => {
                        this.reconnectAttempts = 0;
                        settings.onStatusChange("connected");

                        this.socket.send(
                            JSON.stringify({
                                config: {
                                    sampleRate: settings.config.sampleRate,
                                    languageCode: settings.config.languageCode,
                                    enablePunctuation: true,
                                    interimResults: true,
                                },
                            })
                        );
                    };

                    this.socket.onclose = () => {
                        settings.onStatusChange("disconnected");
                        this.handleReconnect();
                    };

                    this.socket.onerror = (error) => {
                        settings.onError(error);
                    };

                    this.socket.onmessage = (event) => {
                        try {
                            const data = JSON.parse(event.data);
                            if (data.type === "transcript") {
                                settings.onTranscript(data);
                                if (
                                    data.isFinal &&
                                    !this.isRecording &&
                                    this.shutdownCallback
                                ) {
                                    this.pendingAudioProcessing = false;
                                    this.shutdownCallback();
                                }
                            } else if (data.type === "error") {
                                settings.onError(new Error(data.error));
                                this.stop();
                            }
                        } catch (error) {
                            settings.onError(error);
                        }
                    };
                },

                handleAudioProcess(e) {
                    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;

                    const inputData = e.inputBuffer.getChannelData(0);
                    const pcmData = new Int16Array(inputData.length);
                    for (let i = 0; i < inputData.length; i++) {
                        pcmData[i] = Math.max(
                            -32768,
                            Math.min(32767, inputData[i] * 32768)
                        );
                    }

                    this.pendingAudioProcessing = true;

                    this.socket.send(
                        JSON.stringify({
                            audio: this.arrayBufferToBase64(pcmData.buffer),
                        })
                    );
                },

                handleReconnect() {
                    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                        this.options.onError(
                            new Error("Maximum reconnection attempts reached")
                        );
                        return;
                    }

                    this.reconnectAttempts++;

                    clearTimeout(this.reconnectTimeout);
                    this.reconnectTimeout = setTimeout(() => {
                        if (this.isRecording) {
                            this.initializeWebSocket();
                        }
                    }, Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000));
                },

                async updateConfig(config) {
                    this.options = { ...settings, ...config };

                    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                        this.socket.send(
                            JSON.stringify({
                                config: {
                                    sampleRate: this.options.sampleRate,
                                    languageCode: this.options.languageCode,
                                    enablePunctuation: true,
                                    interimResults: true,
                                },
                            })
                        );
                    }
                },

                async stop() {
                    this.isRecording = false;

                    return new Promise((resolve) => {
                        if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
                            this.mediaRecorder.onstop = async () => {
                                try {
                                    const audioBlob = new Blob(this.audioChunks, {
                                        type: "audio/wav",
                                    });
                                    settings.onAudioComplete({ audio: audioBlob });
                                    this.audioChunks = [];
                                } catch (e) {
                                    settings.onError(e);
                                }
                            };
                            this.mediaRecorder.stop();
                        }

                        if (!this.pendingAudioProcessing && !this.socket) {
                            this.cleanup();
                            resolve();
                            return;
                        }

                        this.shutdownCallback = () => {
                            this.cleanup();
                            resolve();
                        };

                        // If socket is open, send end signal to server
                        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                            this.socket.send(JSON.stringify({ command: "end_stream" }));
                        }
                    });
                },

                cleanup() {
                    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
                        this.mediaRecorder.stop();
                    }
                    this.audioChunks = [];

                    if (this.processor) {
                        this.processor.disconnect();
                        this.processor = null;
                    }

                    if (this.analyser) {
                        this.analyser.disconnect();
                        this.analyser = null;
                    }

                    if (this.mediaStream) {
                        this.mediaStream.getTracks().forEach((track) => track.stop());
                        this.mediaStream = null;
                    }

                    if (this.audioContext) {
                        this.audioContext.close();
                        this.audioContext = null;
                    }

                    if (this.socket) {
                        this.socket.close();
                        this.socket = null;
                    }

                    if (this.visualizationFrameId) {
                        cancelAnimationFrame(this.visualizationFrameId);
                        this.visualizationFrameId = null;
                    }

                    clearTimeout(this.reconnectTimeout);
                },

                arrayBufferToBase64(buffer) {
                    const bytes = new Uint8Array(buffer);
                    return btoa(String.fromCharCode.apply(null, bytes));
                },
            };

            transcription.init();
        });
    };
})(jQuery);
