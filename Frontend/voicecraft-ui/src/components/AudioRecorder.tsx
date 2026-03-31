import React, { useState, useRef, useEffect } from 'react';
import { Mic, Square, Trash2, CheckCircle2 } from 'lucide-react';

interface AudioRecorderProps {
  onRecordingComplete: (audioBlob: Blob) => void;
  maxDurationSeconds?: number;
}

export function AudioRecorder({ onRecordingComplete, maxDurationSeconds = 300 }: AudioRecorderProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [audioURL, setAudioURL] = useState<string | null>(null);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      // Cleanup
      if (timerRef.current) clearInterval(timerRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      if (audioURL) URL.revokeObjectURL(audioURL);
    };
  }, [audioURL]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(audioBlob);
        setAudioURL(url);
        onRecordingComplete(audioBlob);
        
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start(250); // timeslice for frequent chunks
      setIsRecording(true);
      setDuration(0);

      timerRef.current = setInterval(() => {
        setDuration((prev) => {
          if (prev >= maxDurationSeconds) {
            stopRecording();
            return prev;
          }
          return prev + 1;
        });
      }, 1000);

    } catch (err) {
      console.error('Microphone access denied:', err);
      alert('Please allow microphone access to record audio.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
    }
  };

  const clearRecording = () => {
    setAudioURL(null);
    audioChunksRef.current = [];
    setDuration(0);
    // Explicitly pass null to parent or assume parent clears it when child resets
    // But since onRecordingComplete expects a Blob, we'll let parent manage removal via their own UI if needed.
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div className="audio-recorder w-full flex flex-col items-center justify-center p-6 border-2 border-dashed border-[var(--glass-border)] rounded-[var(--radius)] bg-[var(--bg-elevated)] relative overflow-hidden transition-colors">
      
      {isRecording && <div className="absolute inset-0 bg-red-500/10 animate-pulse pointer-events-none" />}
      
      {audioURL ? (
        <div className="flex flex-col items-center gap-4 w-full">
          <div className="flex items-center gap-3 text-[var(--green)]">
            <CheckCircle2 size={24} />
            <span className="font-semibold text-lg">Recording Captured</span>
          </div>
          <audio src={audioURL} controls className="w-full max-w-md h-10 accent-[var(--violet)]" />
          <button 
            type="button"
            onClick={clearRecording}
            className="flex items-center gap-2 mt-2 px-4 py-2 text-sm text-[var(--red)] hover:bg-[var(--red-soft)] rounded-md transition-colors"
          >
            <Trash2 size={16} /> Discard and Record Again
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4">
          <div className="text-3xl font-mono text-[var(--text)] tracking-wider">
            {formatTime(duration)}
          </div>
          
          {isRecording ? (
            <button 
              type="button"
              onClick={stopRecording}
              className="group flex items-center justify-center w-16 h-16 rounded-full bg-[var(--red)] hover:bg-red-600 shadow-[var(--shadow)] hover:scale-105 transition-all outline-none focus:ring-4 focus:ring-red-500/30"
              title="Stop Recording"
            >
              <Square size={20} className="text-white fill-white" />
            </button>
          ) : (
            <button 
              type="button"
              onClick={startRecording}
              className="group flex flex-col items-center gap-3 relative"
            >
              <div className="flex items-center justify-center w-16 h-16 rounded-full bg-[var(--violet)] hover:bg-violet-600 shadow-[var(--shadow-violet)] hover:scale-105 transition-all outline-none focus:ring-4 focus:ring-violet-500/30">
                <Mic size={24} className="text-white" />
              </div>
              <span className="text-sm font-medium text-[var(--text-muted)] group-hover:text-[var(--text)] transition-colors">Click to Record</span>
            </button>
          )}

          {isRecording && (
            <div className="text-sm text-[var(--red)] animate-pulse font-medium">Recording in progress...</div>
          )}
        </div>
      )}
    </div>
  );
}
