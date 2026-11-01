import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title:'Loki Cloud', description:'Historical analogue research and model certification' };
export default function Layout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}
