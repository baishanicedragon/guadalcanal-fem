import json, mc_fem as M

# 非破坏性：把配置临时打回 09-23 占位值（jp=1.50 / us=0.55），验证 final1000 旧数的根因
for sc in ("gambler", "historical"):
    M.SCENARIOS[sc]["jp_torp_quality"] = 1.50
    M.SCENARIOS[sc]["us_torp_quality"] = 0.55

res = M.run_sim("gambler", n=1000, seed=42)
print("=== LEGACY (jp=1.50, us=0.55) rerun ===")
print("jp_loss   ", round(res["jp_loss_mean"], 4))
print("us_loss   ", round(res["us_loss_mean"], 4))
print("jp_sunk   ", round(res["jp_sunk_mean"], 3))
print("us_sunk   ", round(res["us_sunk_mean"], 3))
print("yamato    ", round(res["yamato_rate"], 3))
print("he_rounds ", round(res["jp_he_rounds_mean"], 1))
wb = res["us_bb_state_mean"].get("华盛顿", {})
print("Wash dead/struct/guns_ok:", wb.get("dead_rate"), wb.get("struct_loss_mean"), wb.get("guns_ok_mean"))
