'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useTheme } from 'next-themes';
import { AnimatePresence, motion } from 'motion/react';
import { useSessionContext } from '@livekit/components-react';
import { Loader2, ShieldCheck, Sparkles, PhoneCall } from 'lucide-react';
import type { AppConfig } from '@/app-config';
import { AgentSessionView_01 } from '@/components/agents-ui/blocks/agent-session-view-01';
import { WelcomeView } from '@/components/app/welcome-view';
import { CallEndedView } from '@/components/app/call-ended-view';
import { MicPermissionDialog } from '@/components/app/mic-permission-dialog';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionSessionView = motion.create(AgentSessionView_01);
const MotionCallEndedView = motion.create(CallEndedView);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
    },
    hidden: {
      opacity: 0,
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.4,
    ease: 'easeInOut',
  },
};

interface ViewControllerProps {
  appConfig: AppConfig;
}

export function ViewController({ appConfig }: ViewControllerProps) {
  const session = useSessionContext();
  const { isConnected, start } = session;
  const { resolvedTheme } = useTheme();

  // Lifecycle states
  const [hasStartedOnce, setHasStartedOnce] = useState(false);
  const [isConnectingManual, setIsConnectingManual] = useState(false);
  const [hasEnded, setHasEnded] = useState(false);
  const [isMicDialogOpen, setIsMicDialogOpen] = useState(false);
  const [callDuration, setCallDuration] = useState<string | null>(null);
  const callStartTimeRef = React.useRef<number | null>(null);

  // Track active connection to detect when call ends and calculate duration
  useEffect(() => {
    if (isConnected) {
      setHasStartedOnce(true);
      setIsConnectingManual(false);
      setHasEnded(false);
      callStartTimeRef.current = Date.now();
    } else if (hasStartedOnce && !isConnected && !isConnectingManual) {
      // Call was previously connected, now disconnected -> transition to Call Ended state
      if (callStartTimeRef.current) {
        const elapsedSec = Math.max(1, Math.round((Date.now() - callStartTimeRef.current) / 1000));
        const mins = Math.floor(elapsedSec / 60);
        const secs = elapsedSec % 60;
        const formatted = `${mins > 0 ? `${mins}m ` : ''}${secs}s (${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')})`;
        setCallDuration(formatted);
      }
      setHasEnded(true);
    }
  }, [isConnected, hasStartedOnce, isConnectingManual]);

  const handleStartCall = useCallback(async () => {
    // Check if permission is already explicitly denied
    if (typeof navigator !== 'undefined' && navigator.permissions?.query) {
      try {
        const status = await navigator.permissions.query({ name: 'microphone' as PermissionName });
        if (status.state === 'denied') {
          setIsMicDialogOpen(true);
          return;
        }
      } catch {
        // navigator.permissions query for microphone not supported in all browsers; proceed
      }
    }

    try {
      setIsConnectingManual(true);
      setHasEnded(false);
      await start();
    } catch (err: unknown) {
      console.error('Failed to start session:', err);
      setIsConnectingManual(false);
      const errMsg = String(err).toLowerCase();
      if (
        errMsg.includes('permission') ||
        errMsg.includes('notallowed') ||
        errMsg.includes('denied') ||
        errMsg.includes('microphone')
      ) {
        setIsMicDialogOpen(true);
      }
    }
  }, [start]);

  const handleStartAgain = useCallback(() => {
    setHasEnded(false);
    handleStartCall();
  }, [handleStartCall]);

  const isConnecting = isConnectingManual && !isConnected;

  return (
    <>
      <AnimatePresence mode="wait">
        {/* State 1: Ready — Agent has not started yet */}
        {!isConnected && !isConnecting && !hasEnded && (
          <MotionWelcomeView
            key="welcome"
            {...VIEW_MOTION_PROPS}
            startButtonText={appConfig.startButtonText}
            onStartCall={handleStartCall}
          />
        )}

        {/* State 2: Connecting — Agent is joining the call, tell user to wait */}
        {isConnecting && (
          <motion.div
            key="connecting-state"
            {...VIEW_MOTION_PROPS}
            className="flex min-h-[60vh] flex-col items-center justify-center p-6 text-center"
          >
            <div className="bg-card text-card-foreground border-border mx-auto flex w-full max-w-md flex-col items-center rounded-3xl border p-8 shadow-2xl">
              {/* Radar animation */}
              <div className="relative flex size-24 items-center justify-center">
                <span className="absolute size-full animate-ping rounded-full bg-emerald-500/20 duration-1000" />
                <span className="absolute size-16 animate-pulse rounded-full bg-emerald-500/30" />
                <div className="relative flex size-14 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-lg shadow-emerald-600/30">
                  <PhoneCall className="size-6 animate-pulse" />
                </div>
              </div>

              {/* Connecting Badge */}
              <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-teal-600/30 bg-teal-500/10 px-4 py-1.5 text-xs font-semibold text-teal-800 dark:text-teal-300">
                <Loader2 className="size-3.5 animate-spin" />
                <span>Connecting...</span>
              </div>

              {/* Status Message */}
              <h2 className="text-foreground mt-3 text-2xl font-bold tracking-tight">
                Connecting...
              </h2>
              <p className="text-muted-foreground mt-2 text-sm leading-relaxed font-medium">
                Please wait while we connect you.
              </p>

              {/* Micro Guidance */}
              <div className="bg-muted/40 mt-6 flex w-full items-center gap-2.5 rounded-xl border p-3.5 text-left text-xs text-muted-foreground">
                <Sparkles className="size-4 shrink-0 text-teal-600 dark:text-teal-400" />
                <span>Preparing secure audio channel for banking & government schemes...</span>
              </div>
            </div>
          </motion.div>
        )}

        {/* State 5: Call ended — The conversation is over; show option to start again */}
        {hasEnded && !isConnected && !isConnecting && (
          <MotionCallEndedView
            key="call-ended"
            {...VIEW_MOTION_PROPS}
            duration={callDuration}
            onStartAgain={handleStartAgain}
          />
        )}

        {/* States 3 & 4: Active Session (Listening & Speaking) */}
        {isConnected && (
          <MotionSessionView
            key="session-view"
            {...VIEW_MOTION_PROPS}
            supportsChatInput={appConfig.supportsChatInput}
            supportsVideoInput={appConfig.supportsVideoInput}
            supportsScreenShare={appConfig.supportsScreenShare}
            isPreConnectBufferEnabled={appConfig.isPreConnectBufferEnabled}
            audioVisualizerType={appConfig.audioVisualizerType}
            audioVisualizerColor={
              resolvedTheme === 'dark'
                ? appConfig.audioVisualizerColorDark
                : appConfig.audioVisualizerColor
            }
            audioVisualizerColorShift={appConfig.audioVisualizerColorShift}
            audioVisualizerBarCount={appConfig.audioVisualizerBarCount}
            audioVisualizerGridRowCount={appConfig.audioVisualizerGridRowCount}
            audioVisualizerGridColumnCount={appConfig.audioVisualizerGridColumnCount}
            audioVisualizerRadialBarCount={appConfig.audioVisualizerRadialBarCount}
            audioVisualizerRadialRadius={appConfig.audioVisualizerRadialRadius}
            audioVisualizerWaveLineWidth={appConfig.audioVisualizerWaveLineWidth}
            className="fixed inset-0"
          />
        )}
      </AnimatePresence>

      {/* Step 4: Microphone Permission Error Modal */}
      <MicPermissionDialog
        isOpen={isMicDialogOpen}
        onClose={() => setIsMicDialogOpen(false)}
        onRetry={handleStartCall}
      />
    </>
  );
}
