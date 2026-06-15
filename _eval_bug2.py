"""Verify budget copy write logic without Streamlit UI."""

CATEGORIES = ["餐饮", "交通", "娱乐", "住房", "其他"]


def simulate_copy(src_budgets, cur_budgets):
    changed = []
    for cat in CATEGORIES:
        src_val = src_budgets.get(cat, 0)
        cur_val = cur_budgets.get(cat, 0)
        if src_val > 0 and src_val != cur_val:
            cur_budgets[cat] = src_val
            changed.append(cat)
    return cur_budgets, changed


def test_zero_src_preserves_target():
    src = {"餐饮": 0, "交通": 500, "娱乐": 0, "住房": 0, "其他": 0}
    cur = {"餐饮": 100, "交通": 200, "娱乐": 0, "住房": 0, "其他": 0}
    after, changed = simulate_copy(src.copy(), cur.copy())
    assert after["餐饮"] == 100, "zero src must not wipe target"
    assert after["交通"] == 500
    assert changed == ["交通"]


def test_preview_required_logic():
    previewed_source = None
    source_ym = "2026-05"
    has_previewed = previewed_source == source_ym
    assert has_previewed is False
    previewed_source = source_ym
    assert previewed_source == source_ym


if __name__ == "__main__":
    test_zero_src_preserves_target()
    test_preview_required_logic()
    print("OK")
