import json
from dataclasses import asdict
from pathlib import Path
from api.app.lv.pdf import import_with_blocks


def dump_pdf_result():
    pdf_path = Path(r"C:\Users\darme\Desktop\tum-ai-boq-assistant\dataset\LV_00_Roh_und_Erdauarbeiten.pdf")
    result = import_with_blocks(pdf_path.name, pdf_path.read_bytes())

    total_gp = round(sum(p.gp or 0.0 for p in result.lv.positionen), 2)
    print(f"Positions parsed: {len(result.lv.positionen)} | Total GP sum: {total_gp} EUR")

    blocks_serializable = []
    for b in result.blocks:
        b_dict = asdict(b)
        if b_dict["jpeg"] is not None:
            b_dict["jpeg"] = f"<{len(b.jpeg)} bytes JPEG>"
        blocks_serializable.append(b_dict)

    lv_dict = result.lv.model_dump() if hasattr(result.lv, "model_dump") else result.lv.dict()

    output = {
        "total_gp_calculated": total_gp,
        "lv": lv_dict,
        "warnings": result.warnings,
        "blocks": blocks_serializable,
    }

    out_path = Path("pdf_import_output.json")
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    dump_pdf_result()