// Display only: never use the result as a broker symbol or contract identifier.
(()=>{
 const date=value=>{const s=String(value||'').replaceAll('-','');if(!/^\d{8}$/.test(s))return null;const y=+s.slice(0,4),m=+s.slice(4,6),d=+s.slice(6),v=new Date(Date.UTC(y,m-1,d));return v.getUTCFullYear()===y&&v.getUTCMonth()===m-1&&v.getUTCDate()===d?`${s.slice(4,6)}/${s.slice(6)}/${s.slice(2,4)}`:null;};
 const option=(symbol,expiry,strike,right)=>{const day=date(expiry),code={CALL:'C',PUT:'P',C:'C',P:'P'}[String(right||'').toUpperCase()],n=Number(strike);return symbol&&day&&code&&Number.isFinite(n)&&n>0?`${symbol} · ${day} · ${n}${code}`:null;};
 const parse=text=>{const occ=text.match(/^([A-Z0-9.]{1,6})\s*(\d{6})([CP])(\d{8})$/);if(occ)return option(occ[1],'20'+occ[2],Number(occ[4])/1000,occ[3]);const human=text.match(/^(\S+)\s+(\d{8}|\d{4}-\d{2}-\d{2})\s+(\d+(?:\.\d+)?)\s+(CALL|PUT|C|P)$/i);return human?option(human[1],human[2],human[3],human[4]):null;};
 window.WheelContractLabel=value=>{
  if(typeof value==='string')return parse(value)||value;
  const v=value||{},raw=String(v.display_symbol||v.local_symbol||v.label||v.symbol||v.ticker||v.name||''),type=v.security_type||v.secType;
  if(type&&type!=='OPT')return raw;
  // OCC roots preserve adjusted-contract suffixes that a base ticker may omit.
  const occ=parse(String(v.local_symbol||''));
  return occ||option(v.symbol||v.ticker||v.name,v.expiration,v.strike,v.right||v.option_type)||parse(raw)||raw;
 };
})();
