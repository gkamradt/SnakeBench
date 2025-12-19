import { ReactNode } from 'react'
import Navbar from "@/components/layout/Navbar"
import Footer from "@/components/layout/Footer"
import './globals.css'
import 'katex/dist/katex.min.css'
import { PostHogProvider } from "./providers";
import { Press_Start_2P } from "next/font/google"

// Initialize the Press Start 2P font
const pressStart2P = Press_Start_2P({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-press-start-2p",
})

export const metadata = {
  title: 'Snake Bench',
  description: 'Watch AI models compete in Snake battles',
}

export default function RootLayout({
  children,
}: {
  children: ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${pressStart2P.variable} font-sans min-h-screen flex flex-col bg-gray-50`}>
        <PostHogProvider>
          <Navbar />
          <main className="flex-1">
            {children}
          </main>
          <Footer />
        </PostHogProvider>
      </body>
    </html>
  )
}
