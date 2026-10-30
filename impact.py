"""Shortfall from F1 per node: python impact.py <interval> (after python -m rptc.run <interval>)"""
import json,sys
E=10**18; n_=int(sys.argv[1]) if len(sys.argv)>1 else 54
pf=json.load(open(f"cache/rp-performance-mainnet-{n_}.json"))
rf=json.load(open(f"cache/rp-rewards-mainnet-{n_}.json"))
s=json.load(open(f"cache/el-{n_}.json"))
t=rf["totalRewards"]; SP=int(t["totalSmoothingPoolEth"])
mp={n["megapool"].lower():(a,n) for a,n in s["nodes"].items() if n.get("megapoolInfo")}
f_no=5*E//100; f_v=9*E//100
def no_score(b): return (E*b + 32*E*f_no - f_no*b)//(32*E)
def v_score(b): return (32*E*f_v - f_v*b)//(32*E)
recs=[]; A=0; S_pub=0; S_fix=0; V_pub=0; V_fix=0
for v in pf["minipoolPerformance"].values():
    A+=v["successfulAttestations"]; S_pub+=int(v["attestationScore"]); S_fix+=int(v["attestationScore"])
for m,p in pf["megapoolPerformance"].items():
    if "validatorPerformance" not in p: continue
    a,n=mp[m.lower()]; mi=n["megapoolInfo"]; vs=mi["validators"]
    active=mi["activeValidatorCount"]
    funded=sum(1 for v in vs if not v["exited"] and not v["dissolved"] and not v["inQueue"])
    nb=int(mi["nodeBond"])
    b_pub=nb//active if active else 0
    b_fix=nb//funded if funded else 0
    att=sum(x["successfulAttestations"] for x in p["validatorPerformance"].values())
    A+=att
    sp=sum(int(x["attestationScore"]) for x in p["validatorPerformance"].values())
    S_pub+=sp; S_fix+=att*no_score(b_fix)
    V_pub+=att*v_score(b_pub); V_fix+=att*v_score(b_fix)
    recs.append((a,att,sp,att*no_score(b_fix),b_pub,b_fix,active,funded))
# check my reconstruction of published
print("check pub score==att*no_score(b_pub):", all(r[2]==r[1]*no_score(r[4]) for r in recs))
tno_pub=SP*S_pub//(A*E); tno_fix=SP*S_fix//(A*E)
loss=0; rows=[]
for a,att,sp,sf,bp,bf,ac,fu in recs:
    ep=tno_pub*sp//S_pub; ef=tno_fix*sf//S_fix
    if ef-ep>10**12: rows.append((ef-ep,a,round(bp/E,3),round(bf/E,3),ac,fu))
    loss+=max(0,ef-ep)
rows.sort(reverse=True)
print(f"interval {n_}: {len(rows)} megapool nodes underpaid, total {loss/E:.5f} ETH; SP voter pub {SP*V_pub//A//E/E:.5f} fix {SP*V_fix//A//E/E:.5f}")
for r in rows[:8]: print(f"  +{r[0]/E:.5f} ETH {r[1]} bond used {r[2]} vs {r[3]} (active {r[4]}, funded {r[5]})")
json.dump([dict(node=r[1],underpaidWei=str(r[0]),bondUsed=r[2],bondFunded=r[3],activeValidators=r[4],fundedValidators=r[5]) for r in rows],open(f"cache/impact-{n_}.json","w"),indent=1)
