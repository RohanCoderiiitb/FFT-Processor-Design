"""
Main Script for Mixed-Precision FFT Optimization
Orchestrates the complete NSGA-II optimization flow with Vivado integration.

Changes vs original:
  - RTL .v files in results are zipped into rtl_fft{N}.zip and originals deleted
  - Per-run CSV of all evaluated solutions (chromosome, power, area, SQNR)
  - 2-D and 3-D Pareto front plots saved as PNG per FFT size
  - Combined CSV + comparison plot across all FFT sizes
  - main() / default mode runs the full sweep from FFT-2 to FFT-1024
"""

import numpy as np
import os
import shutil
import zipfile
import csv
import glob

import matplotlib
matplotlib.use('Agg')           # non-interactive — safe on headless servers
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.termination import get_termination
from pymoo.optimize import minimize

from globalVariablesMixedFFT import *
from objectiveEvaluationFFT import MixedPrecisionFFTProblem
from optimizationUtils import (
    MyCallback,
    SmartInitialSampling,
    BlockwiseMutation,
    StagewiseCrossover,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def setup_verilog_sources():
    """Copy Verilog source files to the working directory."""
    log_message("Setting up Verilog source files")
    wrapper_src = '../verilog_sources/mixed_precision_wrappers.v'
    wrapper_dst = os.path.join(VERILOG_SOURCES_DIR, 'mixed_precision_wrappers.v')
    if os.path.exists(wrapper_src):
        shutil.copy(wrapper_src, wrapper_dst)
        log_message("Copied wrapper file")


def _sqnr_from_perf_error(perf_error):
    """
    Invert  perf_error = WEIGHT_PERFORMANCE / (sqnr + 1)  back to SQNR (dB).
    Returns inf when perf_error == 0.
    """
    raw_pe = perf_error / WEIGHT_PERFORMANCE
    if raw_pe <= 0:
        return float('inf')
    return 1.0 / raw_pe - 1.0


# ---------------------------------------------------------------------------
# Solution .txt parsing → CSV
# ---------------------------------------------------------------------------

def parse_solution_txts_to_csv(fft_size, results_subdir):
    """
    Parse every  gen{G}_sol{S}.txt  file in RESULTS_DIR that belongs to
    this FFT size (identified by the 'FFT Size' field inside the file) and
    write a single  all_generations_fft{N}.csv  into results_subdir.

    Columns:
        generation, solution_id, fft_size,
        s0_mult, s0_add, s1_mult, s1_add, ...,
        power_W, area_LUTs, sqnr_dB,
        fp4_mult, fp8_mult, fp4_add, fp8_add
    """
    import math, ast as _ast

    num_stages   = int(math.log2(fft_size))
    gene_headers = []
    for s in range(num_stages):
        gene_headers += [f"s{s}_mult", f"s{s}_add"]

    csv_path = os.path.join(results_subdir,
                            f"all_generations_fft{fft_size}.csv")

    pattern  = os.path.join(RESULTS_DIR, "gen*_sol*.txt")
    txt_files = sorted(glob.glob(pattern))

    rows = []
    for fpath in txt_files:
        try:
            data = {}
            with open(fpath) as f:
                for line in f:
                    line = line.strip()
                    # Key : Value lines
                    if ' : ' in line:
                        key, _, val = line.partition(' : ')
                        data[key.strip()] = val.strip()

            # Filter to only files belonging to this FFT size
            if int(data.get('FFT Size', -1)) != fft_size:
                continue

            generation  = int(data['Generation'])
            solution_id = int(data['Solution ID'])
            chrom_raw   = data['Chromosome']          # e.g. "[0, 1, 0, 1, 1, 0]"
            chromosome  = _ast.literal_eval(chrom_raw)
            power       = float(data['Power'].replace(' W', '').strip())
            area        = int(  data['Area'].replace(' LUTs', '').strip())
            sqnr        = float(data['SQNR'].replace(' dB', '').strip())
            fp4_mult    = int(  data.get('FP4 Multipliers', '0').split()[0])
            fp8_mult    = int(  data.get('FP8 Multipliers', '0').split()[0])
            fp4_add     = int(  data.get('FP4 Adders',      '0').split()[0])
            fp8_add     = int(  data.get('FP8 Adders',      '0').split()[0])

            rows.append({
                'generation':  generation,
                'solution_id': solution_id,
                'fft_size':    fft_size,
                'chromosome':  chromosome,
                'power_W':     power,
                'area_LUTs':   area,
                'sqnr_dB':     sqnr,
                'fp4_mult':    fp4_mult,
                'fp8_mult':    fp8_mult,
                'fp4_add':     fp4_add,
                'fp8_add':     fp8_add,
            })
        except Exception as e:
            log_message(f"  Could not parse {fpath}: {e}", level='WARN')

    rows.sort(key=lambda r: (r['generation'], r['solution_id']))

    with open(csv_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            ['generation', 'solution_id', 'fft_size'] +
            gene_headers +
            ['power_W', 'area_LUTs', 'sqnr_dB',
             'fp4_mult', 'fp8_mult', 'fp4_add', 'fp8_add']
        )
        for r in rows:
            chrom = r['chromosome']
            # Pad or truncate chromosome to match expected gene count
            n = num_stages * 2
            chrom = (chrom + [0] * n)[:n]
            writer.writerow(
                [r['generation'], r['solution_id'], r['fft_size']] +
                chrom +
                [f"{r['power_W']:.6f}", r['area_LUTs'],
                 f"{r['sqnr_dB']:.4f}",
                 r['fp4_mult'], r['fp8_mult'],
                 r['fp4_add'],  r['fp8_add']]
            )

    log_message(
        f"All-generations CSV saved → {csv_path}  ({len(rows)} solutions)"
    )
    return txt_files   # return list so caller can pass to the zip function


# ---------------------------------------------------------------------------
# Solution .txt compression (separate zip from RTL)
# ---------------------------------------------------------------------------

def compress_solution_txt_files(fft_size, results_subdir, txt_files):
    """
    Zip the gen*_sol*.txt files that belong to this FFT size into
    solution_logs_fft{N}.zip  inside results_subdir, then delete the originals.

    Kept deliberately separate from rtl_fft{N}.zip so the two archives are
    easy to tell apart.
    """
    if not txt_files:
        log_message("No solution .txt files to compress.", level='WARN')
        return

    zip_path = os.path.join(results_subdir,
                            f"solution_logs_fft{fft_size}.zip")

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for fpath in txt_files:
            zf.write(fpath, os.path.basename(fpath))

    if os.path.exists(zip_path):
        deleted = 0
        for fpath in txt_files:
            try:
                os.remove(fpath)
                deleted += 1
            except OSError as e:
                log_message(
                    f"  Warning: could not remove {fpath}: {e}", level='WARN'
                )
        log_message(
            f"Compressed {len(txt_files)} solution log(s) → {zip_path} "
            f"({deleted} deleted)"
        )
    else:
        log_message("solution_logs zip failed — cleanup skipped.", level='WARN')


# ---------------------------------------------------------------------------
# RTL compression
# ---------------------------------------------------------------------------

def compress_rtl_files(results_subdir, fft_size):
    """
    Zip all generated RTL and simulation files for this FFT size into
    ``rtl_fft{N}.zip``, then delete the originals.

      generated_designs/fft_{N}_*.v    — per-solution RTL cores
      results/fft_{N}/*.v              — any .v copied into results
      sim/tb_fft_{N}_*.v               — auto-generated testbenches
      sim/fft_{N}_*_output.txt         — simulation output vectors
      sim/fft_{N}_*.vvp                — compiled iverilog binaries
      sim/twiddles_1024.txt            — twiddle ROM (included but NOT deleted)
    """
    zip_path = os.path.join(results_subdir, f"rtl_fft{fft_size}.zip")
    zipped_files = []
    sim_dir = os.path.abspath('./sim')

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:

        def _add(filepath, arcdir):
            arcname = os.path.join(arcdir, os.path.basename(filepath))
            zf.write(filepath, arcname)
            zipped_files.append(filepath)

        for f in glob.glob(os.path.join(GENERATED_DESIGNS_DIR,
                                        f"fft_{fft_size}_*.v")):
            _add(f, 'generated_designs')

        for f in glob.glob(os.path.join(results_subdir, '**', '*.v'),
                           recursive=True):
            arcname = os.path.relpath(f, results_subdir)
            zf.write(f, arcname)
            zipped_files.append(f)

        for f in glob.glob(os.path.join(sim_dir, f"tb_fft_{fft_size}_*.v")):
            _add(f, 'sim')

        for f in glob.glob(os.path.join(sim_dir,
                                        f"fft_{fft_size}_*_output.txt")):
            _add(f, 'sim')

        for f in glob.glob(os.path.join(sim_dir, f"fft_{fft_size}_*.vvp")):
            _add(f, 'sim')

        twiddle_file = os.path.join(sim_dir, 'twiddles_1024.txt')
        if os.path.exists(twiddle_file):
            zf.write(twiddle_file, os.path.join('sim', 'twiddles_1024.txt'))
            # shared across runs — do NOT delete

    if os.path.exists(zip_path):
        deleted = sum(1 for f in zipped_files
                      if not (lambda: (os.remove(f), False)[1])())
        log_message(
            f"RTL zip: {len(zipped_files)} file(s) → {zip_path} "
            f"(originals deleted)"
        )
    else:
        log_message("RTL zip creation failed — cleanup skipped.", level='WARN')


def compress_solution_txts(results_subdir, fft_size):
    """
    Parse every ``gen*_sol*.txt`` in RESULTS_DIR that belongs to this FFT run,
    write them all into ``solution_logs_fft{N}.zip`` (kept separate from the
    RTL zip), then delete the originals.

    Also writes ``all_evaluated_solutions_fft{N}.csv`` with one row per file:
        generation, solution_id, fft_size,
        s0_mult, s0_add, ...,
        power_W, area_LUTs, sqnr_dB,
        fp4_mult_pct, fp8_mult_pct, fp4_add_pct, fp8_add_pct
    """
    import re

    txt_files = sorted(glob.glob(os.path.join(RESULTS_DIR, 'gen*_sol*.txt')))
    if not txt_files:
        log_message("No gen*_sol*.txt files found — skipping solution log processing.",
                    level='WARN')
        return

    # ── Parse each file ──────────────────────────────────────────────────
    rows = []
    for path in txt_files:
        try:
            with open(path) as f:
                content = f.read()

            def _field(label):
                m = re.search(rf'^{label}\s*:\s*(.+)$', content, re.MULTILINE)
                return m.group(1).strip() if m else None

            # Only include files that belong to this FFT size
            file_fft = _field('FFT Size')
            if file_fft is None or int(file_fft) != fft_size:
                continue

            generation  = int(_field('Generation') or -1)
            solution_id = int(_field('Solution ID') or -1)
            chromosome_raw = _field('Chromosome')
            chromosome = [int(x) for x in
                          re.findall(r'\d+', chromosome_raw)] if chromosome_raw else []

            power_m = re.search(r'Power\s*:\s*([\d.]+)\s*W',  content)
            area_m  = re.search(r'Area\s*:\s*([\d]+)\s*LUTs', content)
            sqnr_m  = re.search(r'SQNR\s*:\s*([\d.\-]+)\s*dB', content)

            power = float(power_m.group(1)) if power_m else float('nan')
            area  = int(area_m.group(1))    if area_m  else -1
            sqnr  = float(sqnr_m.group(1))  if sqnr_m  else float('nan')

            fp4_mult_m = re.search(r'FP4 Multipliers:\s*\d+\s*\(([\d.]+)%\)', content)
            fp8_mult_m = re.search(r'FP8 Multipliers:\s*\d+\s*\(([\d.]+)%\)', content)
            fp4_add_m  = re.search(r'FP4 Adders\s*:\s*\d+\s*\(([\d.]+)%\)', content)
            fp8_add_m  = re.search(r'FP8 Adders\s*:\s*\d+\s*\(([\d.]+)%\)', content)

            rows.append({
                'generation':   generation,
                'solution_id':  solution_id,
                'fft_size':     fft_size,
                'chromosome':   chromosome,
                'power_W':      power,
                'area_LUTs':    area,
                'sqnr_dB':      sqnr,
                'fp4_mult_pct': float(fp4_mult_m.group(1)) if fp4_mult_m else float('nan'),
                'fp8_mult_pct': float(fp8_mult_m.group(1)) if fp8_mult_m else float('nan'),
                'fp4_add_pct':  float(fp4_add_m.group(1))  if fp4_add_m  else float('nan'),
                'fp8_add_pct':  float(fp8_add_m.group(1))  if fp8_add_m  else float('nan'),
            })

        except Exception as e:
            log_message(f"  Warning: could not parse {path}: {e}", level='WARN')

    # ── Write CSV ────────────────────────────────────────────────────────
    if rows:
        # Build gene column names from the longest chromosome seen
        max_chrom = max(len(r['chromosome']) for r in rows)
        num_stages = max_chrom // 2
        gene_headers = []
        for s in range(num_stages):
            gene_headers += [f"s{s}_mult", f"s{s}_add"]

        csv_path = os.path.join(
            results_subdir, f"all_evaluated_solutions_fft{fft_size}.csv"
        )
        with open(csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                ['generation', 'solution_id', 'fft_size'] +
                gene_headers +
                ['power_W', 'area_LUTs', 'sqnr_dB',
                 'fp4_mult_pct', 'fp8_mult_pct',
                 'fp4_add_pct',  'fp8_add_pct']
            )
            rows.sort(key=lambda r: (r['generation'], r['solution_id']))
            for r in rows:
                # Pad chromosome to full width in case of short entries
                chrom = r['chromosome'] + [0] * (max_chrom - len(r['chromosome']))
                writer.writerow(
                    [r['generation'], r['solution_id'], r['fft_size']] +
                    chrom +
                    [f"{r['power_W']:.6f}", r['area_LUTs'], f"{r['sqnr_dB']:.4f}",
                     f"{r['fp4_mult_pct']:.1f}", f"{r['fp8_mult_pct']:.1f}",
                     f"{r['fp4_add_pct']:.1f}",  f"{r['fp8_add_pct']:.1f}"]
                )
        log_message(
            f"Evaluated-solutions CSV → {csv_path}  ({len(rows)} rows)"
        )

    # ── Zip the txt files ────────────────────────────────────────────────
    zip_path = os.path.join(results_subdir, f"solution_logs_fft{fft_size}.zip")
    zipped = []
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in txt_files:
            try:
                # Only zip files that belong to this FFT size
                with open(path) as f:
                    content = f.read()
                m = re.search(r'^FFT Size\s*:\s*(\d+)', content, re.MULTILINE)
                if m and int(m.group(1)) == fft_size:
                    zf.write(path, os.path.basename(path))
                    zipped.append(path)
            except Exception as e:
                log_message(f"  Warning: could not zip {path}: {e}", level='WARN')

    if os.path.exists(zip_path):
        for path in zipped:
            try:
                os.remove(path)
            except OSError as e:
                log_message(f"  Warning: could not remove {path}: {e}", level='WARN')
        log_message(
            f"Solution-log zip: {len(zipped)} txt file(s) → {zip_path} "
            f"(originals deleted)"
        )
    else:
        log_message("Solution-log zip creation failed — cleanup skipped.",
                    level='WARN')


# ---------------------------------------------------------------------------
# CSV export of all evaluated solutions
# ---------------------------------------------------------------------------

def export_solutions_csv(result, fft_size, results_subdir):
    """
    Write every solution from the final population (plus the Pareto front)
    to  all_solutions_fft{fft_size}.csv.

    Columns:
        solution_id, fft_size,
        s0_mult, s0_add, s1_mult, s1_add, ...,
        power_W, area_LUTs, sqnr_dB, on_pareto_front
    """
    from fft_template_generator import FFTTemplateGenerator
    num_stages = FFTTemplateGenerator(fft_size).num_stages

    gene_headers = []
    for s in range(num_stages):
        gene_headers += [f"s{s}_mult", f"s{s}_add"]

    csv_path = os.path.join(results_subdir, f"all_solutions_fft{fft_size}.csv")

    # Build a set of Pareto-front chromosomes for quick membership test
    pareto_set = set()
    if result.X is not None:
        for row in result.X:
            pareto_set.add(tuple(int(v) for v in row))

    # Gather population arrays
    pop   = result.pop
    all_X = pop.get("X") if pop is not None else np.empty((0, len(gene_headers)))
    all_F = pop.get("F") if pop is not None else np.empty((0, OBJECTIVES))

    # Prepend Pareto front rows and de-duplicate
    if result.X is not None and result.F is not None:
        combined_X = np.vstack([result.X, all_X])
        combined_F = np.vstack([result.F, all_F])
    else:
        combined_X = all_X
        combined_F = all_F

    if len(combined_X) > 0:
        _, unique_idx = np.unique(combined_X, axis=0, return_index=True)
        combined_X = combined_X[unique_idx]
        combined_F = combined_F[unique_idx]

    with open(csv_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            ['solution_id', 'fft_size'] + gene_headers +
            ['power_W', 'area_LUTs', 'sqnr_dB', 'on_pareto_front']
        )
        for idx, (x_row, f_row) in enumerate(zip(combined_X, combined_F)):
            power  = f_row[0] / WEIGHT_POWER
            area   = f_row[1] / WEIGHT_AREA
            sqnr   = _sqnr_from_perf_error(f_row[2])
            on_pf  = int(tuple(int(v) for v in x_row) in pareto_set)
            writer.writerow(
                [idx, fft_size] +
                [int(v) for v in x_row] +
                [f"{power:.6f}", int(area), f"{sqnr:.4f}", on_pf]
            )

    log_message(f"Solution CSV saved → {csv_path}  ({len(combined_X)} rows)")
    return csv_path


# ---------------------------------------------------------------------------
# Pareto front visualisation
# ---------------------------------------------------------------------------

def plot_pareto_front(pareto_objectives, fft_size, results_subdir, feasible=True):
    """
    Save two PNG files per FFT run:
      pareto_2d_fft{N}.png  — three pairwise 2-D scatter plots
      pareto_3d_fft{N}.png  — 3-D scatter (Power vs Area vs SQNR)
    """
    if pareto_objectives is None or len(pareto_objectives) == 0:
        log_message("No objectives to plot — Pareto plots skipped.", level='WARN')
        return

    obj   = np.array(pareto_objectives)
    power = obj[:, 0] / WEIGHT_POWER
    area  = obj[:, 1] / WEIGHT_AREA
    sqnr  = np.array([_sqnr_from_perf_error(pe) for pe in obj[:, 2]])
    sqnr  = np.where(np.isinf(sqnr), np.nan, sqnr)

    status_label = "Pareto Front" if feasible else "Least-Infeasible Solutions"
    color        = "#1f77b4"    if feasible else "#d62728"

    # ── 2-D pairwise plots ───────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(
        f"FFT-{fft_size}  |  {status_label}  ({len(obj)} solutions)",
        fontsize=13, fontweight='bold'
    )
    pairs = [
        (power, area,  "Power (W)",   "Area (LUTs)"),
        (power, sqnr,  "Power (W)",   "SQNR (dB)"),
        (area,  sqnr,  "Area (LUTs)", "SQNR (dB)"),
    ]
    for ax, (xd, yd, xl, yl) in zip(axes, pairs):
        ax.scatter(xd, yd, c=color, alpha=0.75, edgecolors='k',
                   linewidths=0.5, s=60)
        ax.set_xlabel(xl, fontsize=10)
        ax.set_ylabel(yl, fontsize=10)
        ax.set_title(f"{xl} vs {yl}", fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.4)

    plt.tight_layout()
    path_2d = os.path.join(results_subdir, f"pareto_2d_fft{fft_size}.png")
    fig.savefig(path_2d, dpi=150, bbox_inches='tight')
    plt.close(fig)
    log_message(f"2-D Pareto plot saved → {path_2d}")

    # ── 3-D scatter ──────────────────────────────────────────────────────
    fig3d = plt.figure(figsize=(9, 7))
    ax3d  = fig3d.add_subplot(111, projection='3d')
    sc = ax3d.scatter(
        power, area, sqnr,
        c=obj[:, 2], cmap='plasma_r',
        alpha=0.85, edgecolors='k', linewidths=0.4, s=60
    )
    ax3d.set_xlabel("Power (W)",   fontsize=9)
    ax3d.set_ylabel("Area (LUTs)", fontsize=9)
    ax3d.set_zlabel("SQNR (dB)",   fontsize=9)
    ax3d.set_title(
        f"FFT-{fft_size}  |  {status_label}\n(colour = performance error)",
        fontsize=11
    )
    fig3d.colorbar(sc, ax=ax3d, pad=0.1, label='Perf Error')
    path_3d = os.path.join(results_subdir, f"pareto_3d_fft{fft_size}.png")
    fig3d.savefig(path_3d, dpi=150, bbox_inches='tight')
    plt.close(fig3d)
    log_message(f"3-D Pareto plot saved → {path_3d}")


# ---------------------------------------------------------------------------
# Per-FFT-size results saving
# ---------------------------------------------------------------------------

def save_optimization_results(result, callback, fft_size):
    """
    Persist all artefacts for one FFT run:
      • pareto_objectives.npy / pareto_solutions.npy
      • fitness_history.npz
      • summary.txt
      • all_solutions_fft{N}.csv   ← NEW
      • pareto_2d_fft{N}.png       ← NEW
      • pareto_3d_fft{N}.png       ← NEW
      • rtl_fft{N}.zip             ← NEW  (original .v files deleted)
    """
    log_message("Saving optimization results...")

    results_subdir = os.path.join(RESULTS_DIR, f"fft_{fft_size}")
    os.makedirs(results_subdir, exist_ok=True)

    # ── Determine Pareto front (or least-infeasible fallback) ────────────
    pareto_objectives = result.F
    pareto_solutions  = result.X
    feasible = pareto_solutions is not None

    if not feasible:
        log_message(
            "WARNING: No feasible solutions — saving least-infeasible fallback.",
            level='WARN'
        )
        pop = result.pop
        if pop is not None and len(pop) > 0:
            pareto_objectives = pop.get("F")
            pareto_solutions  = pop.get("X")
            cv_vals           = pop.get("CV")
            if cv_vals is not None:
                order             = np.argsort(cv_vals.ravel())
                pareto_objectives = pareto_objectives[order]
                pareto_solutions  = pareto_solutions[order]
        else:
            pareto_objectives = np.empty((0, OBJECTIVES))
            pareto_solutions  = np.empty((0,), dtype=int)

    # ── Persist arrays ───────────────────────────────────────────────────
    np.save(os.path.join(results_subdir, 'pareto_objectives.npy'), pareto_objectives)
    np.save(os.path.join(results_subdir, 'pareto_solutions.npy'),  pareto_solutions)
    np.savez(os.path.join(results_subdir, 'fitness_history.npz'), *callback.data)

    # ── Summary text ─────────────────────────────────────────────────────
    front_label = "Pareto" if feasible else "Fallback"
    summary_file = os.path.join(results_subdir, 'summary.txt')
    with open(summary_file, 'w') as f:
        f.write("Mixed-Precision FFT Optimization Results\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"FFT Size     : {fft_size}\n")
        f.write(f"Population   : {POPULATION}\n")
        f.write(f"Generations  : {GENERATIONS}\n")
        f.write(f"Objectives   : {OBJECTIVES}\n\n")

        if not feasible:
            f.write("*** WARNING: No feasible solutions found. ***\n")
            f.write("Showing least-infeasible solutions from the final population.\n\n")

        f.write(f"{front_label} Front Solutions: {len(pareto_solutions)}\n\n")

        if len(pareto_solutions) == 0:
            f.write("No solutions to report.\n")
        else:
            f.write(f"{'ID':<5} {'Power(W)':<12} {'Area(LUTs)':<12} "
                    f"{'Perf Error':<14} {'SQNR(dB)':<12}\n")
            f.write('-' * 55 + '\n')
            for i, obj in enumerate(pareto_objectives):
                sqnr_approx = _sqnr_from_perf_error(obj[2])
                f.write(f"{i:<5} {obj[0]:<12.6f} {obj[1]:<12.0f} "
                        f"{obj[2]:<14.6f} {sqnr_approx:<12.2f}\n")

            f.write("\n\nBest Solutions by Objective:\n")
            f.write('-' * 50 + '\n')
            for label, col in [
                ("Best Power",       0),
                ("Best Area",        1),
                ("Best Performance", 2),
            ]:
                idx = np.argmin(pareto_objectives[:, col])
                f.write(f"\n{label}:\n")
                f.write(f"  Solution ID : {idx}\n")
                f.write(f"  Power       : {pareto_objectives[idx, 0]:.6f} W\n")
                f.write(f"  Area        : {pareto_objectives[idx, 1]:.0f} LUTs\n")
                f.write(f"  Perf Error  : {pareto_objectives[idx, 2]:.6f}\n")
                f.write(f"  SQNR        : "
                        f"{_sqnr_from_perf_error(pareto_objectives[idx, 2]):.2f} dB\n")
                f.write(f"  Chromosome  : {list(pareto_solutions[idx])}\n")

    # ── CSV of all evaluated solutions ───────────────────────────────────
    export_solutions_csv(result, fft_size, results_subdir)

    # ── Pareto front plots ───────────────────────────────────────────────
    plot_pareto_front(pareto_objectives, fft_size, results_subdir, feasible)

    # ── Parse gen*_sol*.txt → all_generations CSV, then zip+delete them ──
    txt_files = parse_solution_txts_to_csv(fft_size, results_subdir)
    compress_solution_txt_files(fft_size, results_subdir, txt_files)

    # ── Compress RTL files (rtl_fft{N}.zip) — separate from logs ─────────
    compress_rtl_files(results_subdir, fft_size)

    log_message(
        f"Results saved to {results_subdir}  "
        f"({front_label} front: {len(pareto_solutions)} solutions)"
    )


# ---------------------------------------------------------------------------
# Per-size optimisation runner
# ---------------------------------------------------------------------------

def run_optimization_for_fft_size(fft_size):
    """Run NSGA-II optimisation for a specific FFT size; returns pymoo result."""
    import globalVariablesMixedFFT
    globalVariablesMixedFFT.CURRENT_FFT_SIZE = fft_size

    log_message(f"\n{'='*60}")
    log_message(f"Starting optimisation for {fft_size}-point FFT")
    log_message(f"{'='*60}\n")

    problem  = MixedPrecisionFFTProblem(fft_size=fft_size)
    callback = MyCallback()

    algorithm = NSGA2(
        pop_size=POPULATION,
        sampling=SmartInitialSampling(),
        crossover=StagewiseCrossover(fft_size=fft_size, prob=CROSSOVER_RATE),
        mutation=BlockwiseMutation(fft_size=fft_size),
    )
    termination = get_termination("n_gen", GENERATIONS)

    log_message("NSGA-II Configuration:")
    log_message(f"  Population size : {POPULATION}")
    log_message(f"  Generations     : {GENERATIONS}")
    log_message(f"  Crossover rate  : {CROSSOVER_RATE}")
    log_message(f"  Mutation rate   : {MUTATION_RATE}")
    log_message(f"  Objectives      : {OBJECTIVES}")
    log_message(f"  Parallel threads: {SOLUTION_THREADS}")

    result = minimize(
        problem,
        algorithm,
        termination,
        save_history=False,
        callback=callback,
        seed=SEED,
        verbose=VERBOSE,
    )

    log_message(f"Optimisation complete for {fft_size}-point FFT")
    save_optimization_results(result, callback, fft_size)
    return result


# ---------------------------------------------------------------------------
# Full sweep + cross-FFT summary outputs
# ---------------------------------------------------------------------------

def generate_comprehensive_summary(all_results):
    """
    After the full sweep write:
      results/comprehensive_summary.txt
      results/all_pareto_solutions.csv   — combined Pareto rows from all runs
      results/comparison_all_fft_sizes.png
    """
    # ── Text summary ─────────────────────────────────────────────────────
    summary_file = os.path.join(RESULTS_DIR, 'comprehensive_summary.txt')
    with open(summary_file, 'w') as f:
        f.write("Mixed-Precision FFT Optimization — Comprehensive Summary\n")
        f.write("=" * 70 + "\n\n")
        for fft_size, result in sorted(all_results.items()):
            f.write(f"\nFFT Size: {fft_size}\n")
            f.write("-" * 70 + "\n")
            if result is None:
                f.write("  Optimisation failed\n")
                continue
            pf = result.F if result.F is not None else np.empty((0, OBJECTIVES))
            f.write(f"  Pareto front size : {len(pf)}\n")
            if len(pf):
                f.write(f"  Power range       : "
                        f"{pf[:,0].min():.6f} – {pf[:,0].max():.6f} W\n")
                f.write(f"  Area range        : "
                        f"{pf[:,1].min():.0f} – {pf[:,1].max():.0f} LUTs\n")
                f.write(f"  Perf error range  : "
                        f"{pf[:,2].min():.6f} – {pf[:,2].max():.6f}\n")
    log_message(f"Comprehensive summary → {summary_file}")

    # ── Combined CSV across all FFT sizes ────────────────────────────────
    combined_csv = os.path.join(RESULTS_DIR, 'all_pareto_solutions.csv')
    with open(combined_csv, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['fft_size', 'solution_id',
                         'power_W', 'area_LUTs', 'sqnr_dB', 'perf_error'])
        for fft_size, result in sorted(all_results.items()):
            if result is None or result.F is None:
                continue
            for i, obj in enumerate(result.F):
                writer.writerow([
                    fft_size, i,
                    f"{obj[0]/WEIGHT_POWER:.6f}",
                    int(obj[1] / WEIGHT_AREA),
                    f"{_sqnr_from_perf_error(obj[2]):.4f}",
                    f"{obj[2]:.6f}",
                ])
    log_message(f"Combined Pareto CSV   → {combined_csv}")

    # ── Comparison plot: best metric per FFT size ────────────────────────
    sizes, best_power, best_area, best_sqnr = [], [], [], []
    for fft_size, result in sorted(all_results.items()):
        if result is None or result.F is None or len(result.F) == 0:
            continue
        pf = result.F
        sizes.append(fft_size)
        best_power.append(pf[:, 0].min() / WEIGHT_POWER)
        best_area.append(pf[:, 1].min()  / WEIGHT_AREA)
        sqnr_vals = [_sqnr_from_perf_error(pe) for pe in pf[:, 2]]
        finite_sqnr = [v for v in sqnr_vals if not (np.isinf(v) or np.isnan(v))]
        best_sqnr.append(max(finite_sqnr) if finite_sqnr else 0.0)

    if sizes:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        fig.suptitle("Best Achievable Metrics vs FFT Size",
                     fontsize=13, fontweight='bold')
        for ax, ydata, ylabel, color in zip(
            axes,
            [best_power, best_area, best_sqnr],
            ["Min Power (W)", "Min Area (LUTs)", "Max SQNR (dB)"],
            ["#2196F3",       "#FF9800",         "#4CAF50"],
        ):
            ax.plot(sizes, ydata, 'o-', color=color, linewidth=2,
                    markersize=7, markeredgecolor='k', markeredgewidth=0.5)
            ax.set_xlabel("FFT Size (points)", fontsize=10)
            ax.set_ylabel(ylabel, fontsize=10)
            ax.set_title(ylabel, fontsize=11)
            ax.set_xscale('log', base=2)
            ax.set_xticks(sizes)
            ax.set_xticklabels([str(s) for s in sizes], rotation=45, ha='right')
            ax.grid(True, linestyle='--', alpha=0.4)

        plt.tight_layout()
        comp_plot = os.path.join(RESULTS_DIR, 'comparison_all_fft_sizes.png')
        fig.savefig(comp_plot, dpi=150, bbox_inches='tight')
        plt.close(fig)
        log_message(f"Comparison plot       → {comp_plot}")


def run_full_optimization_sweep():
    """Run optimisation for every FFT size in FFT_SIZES (2 – 1024)."""
    log_message("\n" + "=" * 60)
    log_message("Mixed-Precision FFT Optimization Framework")
    log_message("=" * 60 + "\n")

    setup_verilog_sources()
    all_results = {}

    for fft_size in FFT_SIZES:
        try:
            global CURRENT_GEN
            CURRENT_GEN = 0       # reset generation counter per FFT size
            result = run_optimization_for_fft_size(fft_size)
            all_results[fft_size] = result
        except Exception as e:
            log_message(
                f"ERROR: Optimisation failed for {fft_size}-point FFT: {e}",
                level='ERROR'
            )
            all_results[fft_size] = None

    generate_comprehensive_summary(all_results)

    log_message("\n" + "=" * 60)
    log_message("Optimisation sweep complete!")
    log_message("=" * 60)


# ---------------------------------------------------------------------------
# Legacy helper (kept for backward compatibility)
# ---------------------------------------------------------------------------

def quick_test():
    """Quick smoke-test: 16-point FFT with reduced pop/gen."""
    log_message("Running quick test with 16-point FFT")
    setup_verilog_sources()

    global CURRENT_GEN, POPULATION, GENERATIONS
    CURRENT_GEN = 0
    orig_pop, orig_gen = POPULATION, GENERATIONS
    POPULATION, GENERATIONS = 6, 3

    run_optimization_for_fft_size(fft_size=16)

    POPULATION, GENERATIONS = orig_pop, orig_gen
    log_message("Quick test complete")


# ---------------------------------------------------------------------------
# Entry-points
# ---------------------------------------------------------------------------

def main():
    """
    Default entry-point: full sweep across all FFT sizes (2 → 1024).
    Equivalent to  python runMixedFFTOptimization.py --mode full
    """
    # run_full_optimization_sweep()
    quick_test()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Mixed-Precision FFT Optimization using NSGA-II'
    )
    parser.add_argument(
        '--mode',
        choices=['test', 'single', 'full'],
        default='full',
        help=(
            'test   – quick 16-pt smoke test | '
            'single – one FFT size (--fft-size) | '
            'full   – complete sweep 2→1024 (default)'
        ),
    )
    parser.add_argument(
        '--fft-size',
        type=int,
        default=8,
        choices=[2, 4, 8, 16, 32, 64, 128, 256, 512, 1024],
        help='FFT size for --mode single',
    )

    args = parser.parse_args()

    if args.mode == 'test':
        quick_test()
    elif args.mode == 'single':
        setup_verilog_sources()
        run_optimization_for_fft_size(args.fft_size)
    else:
        main()