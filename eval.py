
import os, sys

# Set working directory to the directory containing this script
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(THIS_DIR)
sys.path.append(THIS_DIR)
# Move up to workspace root to allow absolute relative imports if needed
sys.path.append(os.path.abspath(os.path.join(THIS_DIR, "..")))

from commonsense_constraint import evaluation as commonsense_eval
from hard_constraint import evaluation as hard_eval, get_total_cost
from uncertainty_metrics import compute_bas, compute_cats, compute_tdas

import json
from tqdm import tqdm
import argparse
import re



def load_line_json_data(filename):
    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f.read().strip().split('\n'):
            unit = json.loads(line)
            data.append(unit)
    return data


def statistics(constraint_statistic):
    """
    Aggregate constraint results by (level, day, constraint),
    counting only applicable constraints.
    """
    result = {
        level: {day: {} for day in constraint_statistic[level]}
        for level in constraint_statistic
    }

    for level, days in constraint_statistic.items():
        for day, dicts in days.items():
            for dct in dicts:
                if not dct:
                    continue

                for key, value in dct.items():
                    # value is expected to be (bool | None, msg)
                    ok = value[0] if isinstance(value, tuple) else value

                    # NOT applicable
                    if ok is None:
                        continue

                    if key not in result[level][day]:
                        result[level][day][key] = {
                            "true": 0,
                            "false": 0,
                            "total": 0
                        }

                    result[level][day][key]["total"] += 1
                    if ok:
                        result[level][day][key]["true"] += 1
                    else:
                        result[level][day][key]["false"] += 1

    return result

def paper_term_mapping(commonsense_constraint_record, hard_constraint_record):
    mapping_dict = {
        'is_valid_information_in_current_city':'Within Current City',
        'is_valid_information_in_sandbox':'Within Sandbox',
        'is_reasonable_visiting_city':'Reasonable City Route',
        'is_valid_restaurants':'Diverse Restaurants',
        'is_valid_transportation':'Non-conf. Transportation',
        'is_valid_attractions':'Diverse Attractions',
        'is_valid_accommodation':'Minimum Nights Stay',
        'is_not_absent':'Complete Information',
        'valid_cost':'Budget',
        'is_valid_event':'No Reapeated Events',
        'is_valid_meal_gaps':'Sufficient Time between meals',
        'is_valid_poi_sequence':'PoI sequence starts and ends with accommodation',
        'valid_room_rule':'Room Rule',
        'valid_cuisine':'Cuisine',
        'valid_room_type':'Room Type',
        'valid_transportation':'Transportation',
        'valid_event_type':'Event Type',
        'valid_attraction_type':'Attraction Type'
    }

    remap_commonsense_constraint_record = {
        level:{day:{} for day in [3,5,7]} for level in ['easy','medium','hard']
    }
    remap_hard_constraint_record = {
        level:{day:{} for day in [3,5,7]} for level in ['easy','medium','hard']
    }

    for level in commonsense_constraint_record:
        for day in commonsense_constraint_record[level]:
            remap_commonsense_constraint_record[level][day] = {
                mapping_dict.get(key, key): val
                for key, val in commonsense_constraint_record[level][day].items()
            }
            remap_hard_constraint_record[level][day] = {
                mapping_dict.get(key, key): val
                for key, val in hard_constraint_record[level][day].items()
            }

    return remap_commonsense_constraint_record, remap_hard_constraint_record

def eval_score(set_type: str, file_path: str, verbose: bool = False):

    tested_plans = load_line_json_data(file_path)
    query_data_list = [single_plan["JSON"] for single_plan in tested_plans]

    delivery_cnt = 0

    # micro-level counters
    commonsense_pass = 0
    commonsense_total = 0
    hard_pass = 0
    hard_total = 0

    # macro-level counters
    final_commonsense_cnt = 0
    final_hard_cnt = 0
    final_all_cnt = 0

    # detailed storage (unchanged)
    commonsenseConstraint_statistic = {l:{d:[] for d in [3,5,7]} for l in ['easy','medium','hard']}
    hardConstraint_statistic = {l:{d:[] for d in [3,5,7]} for l in ['easy','medium','hard']}

    for idx in range(len(query_data_list)):
        query_data = query_data_list[idx]
        tested_plan = tested_plans[idx]

        if isinstance(query_data, str):
            query_data = eval(query_data)
        if isinstance(tested_plan, str):
            tested_plan = eval(tested_plan)
        if isinstance(query_data["local_constraint"], str):
            query_data["local_constraint"] = eval(query_data["local_constraint"])

        if isinstance(tested_plan["plan"], str):
            s = tested_plan["plan"].strip()
            if not s.startswith("["):
                # Handle cases like "{} {} {}" by converting to "[{}, {}, {}]"
                s = "[" + re.sub(r'}\s+{', '}, {', s) + "]"
            try:
                tested_plan["plan"] = json.loads(s)
            except Exception:
                try:
                    tested_plan["plan"] = eval(s)
                except Exception:
                    # If still fails, try to fix common JSON/Python mismatches for eval
                    try:
                        tested_plan["plan"] = eval(s.replace("null", "None").replace("false", "False").replace("true", "True"))
                    except:
                        # Continue or handle error? For now, we'll try to keep going
                        pass

        if not isinstance(tested_plan["plan"], list) or len(tested_plan["plan"]) <= 2:
            continue
        delivery_cnt += 1

        # ---------- Commonsense ----------
        commonsense_info = commonsense_eval(query_data, tested_plan["plan"])
        commonsenseConstraint_statistic[query_data["level"]][query_data["days"]].append(commonsense_info)

        if verbose:
            print("\n*** Commonsense Constraint ***")
            for k, v in commonsense_info.items():
                print(f"{k}: {v}")
            print("*** Commonsense Constraint Ends ***")

        plan_commonsense_pass = True
        for k, (ok, _) in commonsense_info.items():
            commonsense_total += 1
            if ok:
                commonsense_pass += 1
            else:
                plan_commonsense_pass = False

        if plan_commonsense_pass:
            final_commonsense_cnt += 1

        # ---------- Total cost ----------
        if verbose:
            import math
            total_cost = get_total_cost(query_data, tested_plan["plan"])
            if math.isnan(total_cost):
                total_cost = 0.0
            print(round(total_cost, 2))

        # ---------- Hard constraints ----------
        hard_info = hard_eval(query_data, tested_plan["plan"])
        hardConstraint_statistic[query_data["level"]][query_data["days"]].append(hard_info)

        if verbose:
            print("*** Hard Constraint ***")
            for k, v in hard_info.items():
                ok_val = v[0] if isinstance(v, tuple) else v
                if ok_val is None:
                    # Not applicable → treat as passing
                    display_v = (True, None)
                else:
                    # Convert numpy bools to native Python bool for clean display
                    display_v = (bool(v[0]) if hasattr(v[0], 'item') else v[0], v[1])
                print(f"{k}: {display_v}")
            print("*** Hard Constraint Ends ***")

        # ---------- Uncertainty Metrics ----------
        if verbose:
            print("\n*** Uncertainty Metrics ***")

            bas_score, bas_lines = compute_bas(query_data, tested_plan["plan"])
            print("  -- BAS (Buffer Adequacy Score) --")
            for l in bas_lines:
                print(l)
            if bas_score is not None:
                print(f"  Trip BAS: {bas_score:.4f}")

            cats_score, cats_lines = compute_cats(query_data, tested_plan["plan"])
            print("  -- CATS (Crowd-Aware Timing Score) --")
            for l in cats_lines:
                print(l)
            if cats_score is not None:
                print(f"  Trip CATS: {cats_score:.4f}")

            tdas_score, tdas_lines = compute_tdas(query_data, tested_plan["plan"])
            print("  -- TDAS (Travel Delay Adequacy Score) --")
            for l in tdas_lines:
                print(l)
            if tdas_score is not None:
                print(f"  Trip TDAS: {tdas_score:.4f}")

            print("*** Uncertainty Metrics Ends ***")

        plan_hard_pass = True

        for k, (ok, _) in hard_info.items():
            # applicability check
            if ok is None:
                continue

            hard_total += 1
            if ok:
                hard_pass += 1
            else:
                plan_hard_pass = False

        # no applicable hard constraints → vacuously true
        if hard_total == 0 or plan_hard_pass:
            final_hard_cnt += 1

        if plan_commonsense_pass and plan_hard_pass:
            final_all_cnt += 1

    # ---------- Metrics ----------
    result = {}

    dataset_size = {
        "3d": 150,
        "5d": 150,
        "7d": 150,
        "custom": max(delivery_cnt, 1)  # use actual sample count for custom
    }[set_type]

    result["Delivery Rate"] = delivery_cnt / dataset_size

    # Avoid division by zero when no commonsense constraints were applicable
    result["Commonsense Constraint Micro Pass Rate"] = (
        1.0 if commonsense_total == 0 else commonsense_pass / commonsense_total
    )
    result["Commonsense Constraint Macro Pass Rate"] = final_commonsense_cnt / dataset_size

    # Hard constraints already treat "no applicable" as fully satisfied
    result["Hard Constraint Micro Pass Rate"] = (
        1.0 if hard_total == 0 else hard_pass / hard_total
    )
    result["Hard Constraint Macro Pass Rate"] = final_hard_cnt / dataset_size
    result["Final Pass Rate"] = final_all_cnt / dataset_size

    # ---------- detailed tables (unchanged pipeline) ----------
    commonsense_processed = statistics(commonsenseConstraint_statistic)
    hard_processed = statistics(hardConstraint_statistic)

    remap_commonsense, remap_hard = paper_term_mapping(
        commonsense_processed, hard_processed
    )

    return result, {
        "Commonsense Constraint": remap_commonsense,
        "Hard Constraint": remap_hard
    }

def explain_plan(query_data, tested_plan):
    """
    Explain why a SINGLE plan failed.
    Returns a list of failed constraints with reasons.
    """

    explanations = []

    # ---------- Commonsense constraints ----------
    commonsense_info = commonsense_eval(query_data, tested_plan["plan"])

    for cname, (ok, msg) in commonsense_info.items():
        if ok is False:
            explanations.append({
                "constraint": cname,
                "reason": msg
            })

    # ---------- Hard constraints (gating removed to avoid missing keys) ----------
    # if (
    #     commonsense_info.get("is_not_absent", (True, None))[0] and
    #     commonsense_info.get("is_valid_information_in_sandbox", (True, None))[0]
    # ):
    hard_info = hard_eval(query_data, tested_plan["plan"])

    for cname, (ok, msg) in hard_info.items():
        if ok is False:
            explanations.append({
                "constraint": cname,
                "reason": msg
            })

    return explanations

def explain(idx, file_path="/"):
    """
    Single-line helper:
    explain(1) → explains the plan whose JSON field "idx" == 1
    phi4_5day_llm.jsonl
    """

    plans = load_line_json_data(file_path)

    # 🔍 find plan by internal idx
    matched = None
    for plan in plans:
        if plan.get("idx") == idx:
            matched = plan
            break

    if matched is None:
        print(f"❌ No plan present with idx = {idx}")
        return

    query = matched["JSON"]

    reasons = explain_plan(query, matched)

    if not reasons:
        print(f"✅ Plan with idx = {idx} has NO violations")
        return

    print(f"\n🔎 PLAN idx = {idx} FAILURES:")
    for r in reasons:
        print(f"❌ {r['constraint']} → {r['reason']}")


def explain_batch(start_idx, end_idx, file_path="/"):
    plans = load_line_json_data(file_path)
    plan_map = {p.get("idx"): p for p in plans}

    for idx in range(start_idx, end_idx + 1):
        matched = plan_map.get(idx)
        if not matched:
            continue

        reasons = explain_plan(matched["JSON"], matched)

        if not reasons:
            continue  # ✅ skip valid plans

        print("\n" + "=" * 60)
        print(f"🔎 PLAN idx = {idx} FAILURES:")
        for r in reasons:
            print(f"❌ {r['constraint']} → {r['reason']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--set_type", type=str, default="validation")
    parser.add_argument("--evaluation_file_path", type=str, default="./")
    parser.add_argument("--verbose", action="store_true", default=False,
                        help="Print per-plan constraint results (useful for annotators)")
    args = parser.parse_args()

    # custom mode defaults to verbose for the annotator helper
    verbose = args.verbose or (args.set_type == "custom")

    scores, detailed_scores = eval_score(
        args.set_type,
        file_path=args.evaluation_file_path,
        verbose=verbose
    )

    # ---------- Print overall scores ----------
    for key in scores:
        print(f"{key}: {scores[key]*100}%")

    print("------------------")

    # ---------- FILTER detailed scores by set_type ----------
    if args.set_type == "custom":
        filtered_details = detailed_scores
    else:
        target_day = int(args.set_type[0])  # "3d" -> 3, "5d" -> 5, "7d" -> 7

        filtered_details = {}

        for constraint_type, level_dict in detailed_scores.items():
            filtered_details[constraint_type] = {}
            for level, day_dict in level_dict.items():
                # keep only the relevant day bucket
                if target_day in day_dict and day_dict[target_day]:
                    filtered_details[constraint_type][level] = {
                        target_day: day_dict[target_day]
                    }
                else:
                    filtered_details[constraint_type][level] = {}

    print(filtered_details)
    print("------------------")

