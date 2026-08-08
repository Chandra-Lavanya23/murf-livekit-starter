'use client';

import React from 'react';
import {
  Landmark,
  ShieldAlert,
  CreditCard,
  Building2,
  PhoneCall,
  Lock,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/components/app/language-context';
import { LanguageSelector } from '@/components/app/language-selector';

interface WelcomeViewProps {
  startButtonText?: string;
  onStartCall: () => void;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  const { t, currentLanguageOption } = useLanguage();

  const featureCards = [
    {
      title: t.govSchemes,
      description: t.govSchemesDesc,
      icon: Building2,
      tag: 'Welfare & Benefits',
    },
    {
      title: t.bankingBasics,
      description: t.bankingBasicsDesc,
      icon: Landmark,
      tag: 'Accounts & Savings',
    },
    {
      title: t.upiSafety,
      description: t.upiSafetyDesc,
      icon: CreditCard,
      tag: 'Digital Payments',
    },
    {
      title: t.fraudAwareness,
      description: t.fraudAwarenessDesc,
      icon: ShieldAlert,
      tag: 'Cyber Protection',
    },
  ];

  return (
    <div
      ref={ref}
      className="relative flex min-h-screen w-full flex-col items-center justify-center px-4 py-10 md:py-16"
    >
      {/* Background Soft Glow */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden">
        <div className="h-[400px] w-[600px] rounded-full bg-teal-500/10 blur-3xl dark:bg-teal-500/15" />
      </div>

      <section className="relative z-10 flex w-full max-w-4xl flex-col items-center text-center">
        {/* Top Bar: Ready State Badge & Language Selector */}
        <div className="relative z-30 mb-4 flex flex-wrap items-center justify-center gap-2.5 pointer-events-auto">
          <div className="inline-flex items-center gap-2 rounded-full border border-teal-600/30 bg-teal-500/10 px-4 py-1.5 text-xs font-semibold text-teal-800 dark:text-teal-300">
            <span className="relative flex size-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75" />
              <span className="relative inline-flex size-2.5 rounded-full bg-teal-600 dark:bg-teal-400" />
            </span>
            <span>{t.readyToHelp}</span>
            <span className="text-teal-600/40">•</span>
            <span className="text-[11px] font-normal opacity-90">Auto Voice Detection</span>
          </div>

          <LanguageSelector variant="header" />
        </div>

        {/* Banking Icon Emblem */}
        <div className="relative mb-5 flex size-20 items-center justify-center rounded-3xl bg-linear-to-br from-teal-700 to-slate-900 text-white shadow-xl shadow-teal-900/20">
          <Landmark className="size-10 text-teal-200" />
          <div className="absolute -bottom-1 -right-1 flex size-7 items-center justify-center rounded-full bg-amber-500 text-white shadow-md">
            <ShieldCheck className="size-4" />
          </div>
        </div>

        {/* Title */}
        <h1 className="text-foreground text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
          {t.appTitle}
        </h1>

        {/* Subtitle */}
        <p className="text-muted-foreground mt-3 max-w-2xl text-base leading-relaxed sm:text-lg">
          {t.appSubtitle}
        </p>

        {/* Indian User Greeting */}
        <div className="mt-4 inline-flex items-center gap-2 rounded-2xl border border-border/80 bg-card/70 px-4 py-2 text-sm font-semibold text-foreground backdrop-blur-xs shadow-xs">
          <span>🙏</span>
          <span className="text-teal-700 dark:text-teal-300">{t.greeting}</span>
        </div>

        {/* Feature Cards Grid (4 Core Areas) */}
        <div className="mt-7 grid w-full grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
          {featureCards.map((card) => {
            const Icon = card.icon;
            return (
              <div
                key={card.title}
                className="group bg-card/80 border-border/80 hover:border-teal-500/50 hover:bg-card flex flex-col justify-between rounded-2xl border p-4 text-left shadow-xs transition-all hover:shadow-md backdrop-blur-xs"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex size-10 items-center justify-center rounded-xl bg-teal-500/10 text-teal-700 dark:bg-teal-400/15 dark:text-teal-300">
                      <Icon className="size-5" />
                    </div>
                    <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                      {card.tag}
                    </span>
                  </div>
                  <h2 className="text-foreground mt-3 text-sm font-bold tracking-tight">
                    {card.title}
                  </h2>
                  <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
                    {card.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Large, Easy-to-Tap Start Button (State 1: Ready) */}
        <div className="mt-9 flex w-full flex-col items-center">
          <Button
            size="lg"
            onClick={onStartCall}
            className="group bg-teal-700 hover:bg-teal-800 text-white h-14 w-full max-w-sm rounded-2xl text-base font-bold shadow-xl shadow-teal-800/25 transition-all hover:scale-105 active:scale-95 cursor-pointer"
          >
            <PhoneCall className="mr-2.5 size-5 transition-transform group-hover:rotate-12" />
            {t.startConversation}
            <ArrowRight className="ml-2.5 size-4 opacity-70 transition-transform group-hover:translate-x-1" />
          </Button>

          <p className="text-muted-foreground mt-3.5 flex items-center gap-1.5 text-xs">
            <Lock className="size-3.5 text-teal-600 dark:text-teal-400" />
            <span>
              Spoken guidance in {currentLanguageOption.name} ({currentLanguageOption.nativeName}) & auto detection.
            </span>
          </p>
        </div>
      </section>

      {/* Trust & Verification Footer */}
      <footer className="mt-12 flex flex-wrap items-center justify-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <CheckCircle2 className="size-3.5 text-teal-600 dark:text-teal-400" />
          Indian Financial & Welfare Schemes
        </span>
        <span>•</span>
        <span className="flex items-center gap-1.5">
          <ShieldCheck className="size-3.5 text-teal-600 dark:text-teal-400" />
          Safe Banking & UPI Anti-Fraud
        </span>
      </footer>
    </div>
  );
};
