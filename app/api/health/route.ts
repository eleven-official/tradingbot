import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    app: 'loki-tradingbot',
    timestamp: new Date().toISOString()
  });
}
