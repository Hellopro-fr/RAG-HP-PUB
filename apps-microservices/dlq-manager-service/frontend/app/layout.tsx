import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

const _geist = Geist({ subsets: ["latin"] });
const _geistMono = Geist_Mono({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: 'Hellopro DLQ Manager',
  description: 'Manage and monitor your Dead Letter Queues with ease.',
  generator: 'Next.js',
  robots: {
    index: false,
    follow: false,
  },
  icons: {
    icon: 'https://www.hellopro.fr/hellopro_fr/images/hp-logo.svg',
    apple: 'https://www.hellopro.fr/hellopro_fr/images/hp-logo.svg',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`font-sans antialiased`}>
        {children}
        <Analytics />
      </body>
    </html>
  )
}