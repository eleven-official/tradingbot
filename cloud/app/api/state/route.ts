import { authenticated } from '../../../lib/server';
import { failure } from '../../../lib/http';
export const dynamic='force-dynamic';
export async function GET(request:Request) {
  try{
    const {db,user}=await authenticated(request);
    const queries=await Promise.all([
      db.from('profiles').select('display_name,role').eq('id',user.id).maybeSingle(),
      db.from('market_datasets').select('id,symbol,asset_kind,timeframe,requested_years,status,source,source_verified,raw_count,feature_count,last_error').eq('user_id',user.id).order('created_at',{ascending:false}).limit(20),
      db.from('ai_optimization_jobs').select('id,dataset_id,status,work,max_trials,updated_at').eq('user_id',user.id).order('created_at',{ascending:false}).limit(20),
      db.from('ai_optimization_runs').select('id,job_id,trial,stage,metrics,qualified,created_at').eq('user_id',user.id).order('created_at',{ascending:false}).limit(50),
      db.from('trade_logs').select('id,symbol,asset_kind,side,status,quantity,filled_quantity,average_fill,realized_pnl,created_at').eq('user_id',user.id).order('created_at',{ascending:false}).limit(50),
      db.from('equity_snapshots').select('equity,cash,positions,source,observed_at').eq('user_id',user.id).order('observed_at',{ascending:false}).limit(100),
    ]);
    if(queries.some(q=>q.error))throw new Error('Database query failed');
    return Response.json({profile:queries[0].data||{role:'researcher'},datasets:queries[1].data,jobs:queries[2].data,runs:queries[3].data,trades:queries[4].data,equity:queries[5].data},{headers:{'Cache-Control':'private, no-store'}});
  }catch(error){return failure(error);}
}
