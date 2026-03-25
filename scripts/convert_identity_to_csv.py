import json
import csv
import os

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────
INPUT_FILE  = r"C:\RAG\documents\IdentityAccess.json"
OUTPUT_DIR  = r"C:\RAG\documents\processed"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────
# HELPER — flatten a dict, skip nulls
# ─────────────────────────────────────────
def flatten(obj, prefix="", max_depth=3, depth=0):
    result = {}
    if depth > max_depth or not isinstance(obj, dict):
        return result
    for key, val in obj.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}_{key}"
        if val is None:
            continue  # skip nulls entirely
        elif isinstance(val, dict):
            nested = flatten(val, full_key, max_depth, depth+1)
            result.update(nested)
        elif isinstance(val, list):
            non_null = [str(v) for v in val if v is not None]
            if non_null:
                result[full_key] = "; ".join(non_null)
        else:
            result[full_key] = str(val)
    return result

def write_csv(records, output_path, label):
    if not records:
        print(f"  ⚠️  {label} — no records, skipping")
        return 0

    # Collect all possible columns across all records
    all_keys = []
    seen_keys = set()
    flat_records = []
    for record in records:
        if not isinstance(record, dict):
            continue
        flat = flatten(record)
        flat_records.append(flat)
        for k in flat.keys():
            if k not in seen_keys:
                all_keys.append(k)
                seen_keys.add(k)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for row in flat_records:
            writer.writerow(row)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"  ✅ {label}")
    print(f"     → {output_path}")
    print(f"     → {len(flat_records):,} rows | {len(all_keys)} columns | {size_kb:.1f} KB")
    return len(flat_records)

# ─────────────────────────────────────────
# LOAD JSON
# ─────────────────────────────────────────
print("\n[1/3] Loading IdentityAccess.json (313MB)...")
print("      This will take 1-2 minutes...")

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

print("      Loaded successfully!\n")

# ─────────────────────────────────────────
# EXTRACT TENANT INFO
# ─────────────────────────────────────────
print("[2/3] Extracting sections...\n")

tenant = data.get("Tenant", {})
if tenant:
    path = os.path.join(OUTPUT_DIR, "identity_tenant.csv")
    write_csv([tenant], path, "Tenant Info")

# ─────────────────────────────────────────
# EXTRACT PIM ROLE ASSIGNMENTS
# ─────────────────────────────────────────
pim_records = data.get("PIMRoleAssignments", [])
write_csv(
    pim_records,
    os.path.join(OUTPUT_DIR, "identity_pim.csv"),
    "PIM Role Assignments"
)

# ─────────────────────────────────────────
# EXTRACT GUEST USERS
# ─────────────────────────────────────────
guest_records = data.get("GuestUsers", [])
write_csv(
    guest_records,
    os.path.join(OUTPUT_DIR, "identity_guests.csv"),
    "Guest Users"
)

# ─────────────────────────────────────────
# EXTRACT MFA REGISTRATION DETAILS
# ─────────────────────────────────────────
mfa_records = data.get("MfaRegistrationDetails", [])
write_csv(
    mfa_records,
    os.path.join(OUTPUT_DIR, "identity_mfa.csv"),
    "MFA Registration Details"
)

# ─────────────────────────────────────────
# EXTRACT HIGH PRIVILEGE APP REGISTRATIONS
# ─────────────────────────────────────────
app_records = data.get("HighPrivilegeAppRegistrations", [])
write_csv(
    app_records,
    os.path.join(OUTPUT_DIR, "identity_apps.csv"),
    "High Privilege App Registrations"
)

# ─────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────
print("\n[3/3] Summary")
print("=" * 60)
print(f"  Output folder : {OUTPUT_DIR}")
print(f"\n  Files created:")
for f in os.listdir(OUTPUT_DIR):
    if f.endswith(".csv"):
        size = os.path.getsize(os.path.join(OUTPUT_DIR, f)) / 1024
        print(f"    - {f} ({size:.1f} KB)")
print(f"\n  Next step: run ingest_multi.py targeting processed folder")
print("=" * 60)