import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

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
      <body className={`${geist.variable} ${geistMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  )
}