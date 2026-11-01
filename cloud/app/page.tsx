import { redirect } from 'next/navigation';
import { server } from '../lib/server';
import Dashboard from '../components/Dashboard';
export const dynamic='force-dynamic';
export default async function Home() {
  const db=await server();const {data}=await db.auth.getUser();
  if(!data.user)redirect('/login');
  return <Dashboard email={data.user.email||'Signed in'}/>;
}
