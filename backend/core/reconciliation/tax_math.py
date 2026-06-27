from typing import Dict, Any, List

class TaxMathematicsEngine:
    """
    Stage 4: Executes independent tax verification paths (Path A to E) 
    and selects the optimal path based on minimal variance.
    """
    def __init__(self, tolerance: float = 1.50):
        self.tolerance = tolerance

    def evaluate_paths(self, data: Dict[str, float]) -> Dict[str, Any]:
        """
        Evaluates Paths A-E and picks the best match.
        """
        taxable = data.get("taxable", 0.0)
        cgst = data.get("cgst", 0.0)
        sgst = data.get("sgst", 0.0)
        igst = data.get("igst", 0.0)
        total = data.get("total", 0.0)
        gross = data.get("gross", taxable)
        discount = data.get("discount", 0.0)
        freight = data.get("freight", 0.0)
        packing = data.get("packing", 0.0)
        insurance = data.get("insurance", 0.0)
        other_charges = data.get("other_charges", 0.0)
        
        tax_total = cgst + sgst + igst
        
        # Path A
        path_a_calc = taxable + cgst + sgst
        variance_a = abs(path_a_calc - total)
        
        # Path B
        path_b_calc = taxable + igst
        variance_b = abs(path_b_calc - total)
        
        # Path C
        path_c_calc = gross - discount + tax_total
        variance_c = abs(path_c_calc - total)
        
        # Path D
        path_d_calc = gross + tax_total - discount
        variance_d = abs(path_d_calc - total)
        
        # Path E
        path_e_calc = gross - discount + freight + packing + insurance + other_charges + tax_total
        variance_e = abs(path_e_calc - total)
        
        paths = [
            {"path": "Path A", "variance": variance_a, "confidence": 1.0 - (variance_a / total if total > 0 else 0), "explanation": "Taxable + CGST + SGST = Total", "assumptions": "Intrastate CGST/SGST transaction"},
            {"path": "Path B", "variance": variance_b, "confidence": 1.0 - (variance_b / total if total > 0 else 0), "explanation": "Taxable + IGST = Total", "assumptions": "Interstate IGST transaction"},
            {"path": "Path C", "variance": variance_c, "confidence": 1.0 - (variance_c / total if total > 0 else 0), "explanation": "Gross - Discount + Tax = Total", "assumptions": "Pre-tax discount applied"},
            {"path": "Path D", "variance": variance_d, "confidence": 1.0 - (variance_d / total if total > 0 else 0), "explanation": "Gross + Tax - Discount = Total", "assumptions": "Post-tax discount applied"},
            {"path": "Path E", "variance": variance_e, "confidence": 1.0 - (variance_e / total if total > 0 else 0), "explanation": "Gross - Discount + Auxiliary Charges + Tax = Total", "assumptions": "Pre-tax discount and auxiliary logistics charges"}
        ]
        
        # Select path with lowest variance
        best_path = min(paths, key=lambda x: x["variance"])
        
        return {
            "winning_path": best_path["path"],
            "variance": best_path["variance"],
            "confidence": max(0.0, best_path["confidence"]),
            "explanation": best_path["explanation"],
            "assumptions": best_path["assumptions"],
            "verified": best_path["variance"] <= self.tolerance,
            "all_paths": paths
        }
