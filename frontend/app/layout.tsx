import { Public_Sans } from 'next/font/google';
import localFont from 'next/font/local';
import { headers } from 'next/headers';
import { ThemeProvider } from '@/components/app/theme-provider';
import { ThemeToggle } from '@/components/app/theme-toggle';
import { cn } from '@/lib/shadcn/utils';
import { getAppConfig, getStyles } from '@/lib/utils';
import '@/styles/globals.css';

const publicSans = Public_Sans({
  variable: '--font-public-sans',
  subsets: ['latin'],
});

const commitMono = localFont({
  display: 'swap',
  variable: '--font-commit-mono',
  src: [
    {
      path: '../fonts/CommitMono-400-Regular.otf',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-700-Regular.otf',
      weight: '700',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-400-Italic.otf',
      weight: '400',
      style: 'italic',
    },
    {
      path: '../fonts/CommitMono-700-Italic.otf',
      weight: '700',
      style: 'italic',
    },
  ],
});

interface RootLayoutProps {
  children: React.ReactNode;
}

import { LanguageProvider } from '@/components/app/language-context';

export default async function RootLayout({ children }: RootLayoutProps) {
  const hdrs = await headers();
  const appConfig = await getAppConfig(hdrs);
  const styles = getStyles(appConfig);
  const { pageTitle, pageDescription, companyName, logo, logoDark } = appConfig;

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        publicSans.variable,
        commitMono.variable,
        'scroll-smooth font-sans antialiased'
      )}
    >
      <head>
        {styles && <style>{styles}</style>}
        <title>{pageTitle}</title>
        <meta name="description" content={pageDescription} />
      </head>
      <body className="overflow-x-hidden">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <LanguageProvider>
            <header className="fixed top-0 left-0 z-40 hidden w-full flex-row items-center justify-between p-6 pointer-events-none md:flex">
              <div className="flex items-center gap-3 pointer-events-auto">
                <div className="flex size-9 items-center justify-center rounded-xl bg-teal-700 text-white font-bold text-sm shadow-md">
                  ₹
                </div>
                <div className="flex flex-col">
                  <span className="text-foreground text-sm font-bold tracking-tight">
                    Financial Services Assistant
                  </span>
                  <span className="text-muted-foreground text-[10px] uppercase tracking-wider font-semibold">
                    Smarter & Safer Financial Decisions
                  </span>
                </div>
              </div>
              <span className="text-foreground font-mono text-xs font-bold tracking-wider uppercase inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-card/60 px-3.5 py-1 backdrop-blur-xs pointer-events-auto">
                <span className="size-2 rounded-full bg-teal-500 animate-pulse" />
                LiveKit & Murf Voice
              </span>
            </header>

            {children}
            <div className="group fixed bottom-0 left-1/2 z-50 mb-2 -translate-x-1/2">
              <ThemeToggle className="translate-y-20 transition-transform delay-150 duration-300 group-hover:translate-y-0" />
            </div>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
