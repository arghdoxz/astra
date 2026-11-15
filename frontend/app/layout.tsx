import type { Metadata, Viewport } from "next";
import { Source_Serif_4, Public_Sans, Courier_Prime } from "next/font/google";
import "./globals.css";
import Nav from "@/components/layout/Nav";
import Footer from "@/components/layout/Footer";
import PlateBackdrop from "@/components/layout/PlateBackdrop";

// Plate-archive type: a book serif for headings, a plain public-sector sans for the UI,
// and a typewriter face for plate labels, coordinates and numbers.
const serif = Source_Serif_4({
  variable: "--font-serif",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  display: "swap",
});
const ui = Public_Sans({
  variable: "--font-ui",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});
const type = Courier_Prime({
  variable: "--font-type",
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ASTRA · SPHEREx time-domain explorer",
  description:
    "Investigate real NASA SPHEREx infrared observations over time: movers, variables and 0.75–5 µm spectra, with evidence you can check. Not affiliated with or endorsed by NASA.",
};

export const viewport: Viewport = {
  themeColor: "#e3e6e4",
  colorScheme: "light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${serif.variable} ${ui.variable} ${type.variable}`}>
      <body className="min-h-screen flex flex-col">
        <PlateBackdrop />
        <Nav />
        <div className="flex-1 flex flex-col">{children}</div>
        <Footer />
      </body>
    </html>
  );
}
