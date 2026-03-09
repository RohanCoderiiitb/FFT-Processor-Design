# ⚡ Mixed-Precision FFT Processor

## 🧠 Overview

This project explores **precision-aware hardware design for FFT
accelerators**.\
The goal is to study how reduced-precision floating-point arithmetic can
improve **power and area efficiency** while maintaining acceptable
numerical accuracy.

The system implements a **parameterized Decimation-in-Time (DIT) FFT
processor** supporting transform sizes from:

**8 → 1024 points**

The architecture uses custom floating‑point formats:

-   **FP4 (E2M1)** -- ultra low precision
-   **FP8 (E4M3)** -- higher dynamic range

Instead of forcing one precision across the entire pipeline, the project
investigates **mixed‑precision FFT architectures**, where **different
stages of the FFT can use different precisions**.

------------------------------------------------------------------------

# 🔬 Research Motivation

Signal processing algorithms are typically designed assuming:

-   infinite numerical precision\
-   ideal computation

Real hardware must operate under constraints such as:

-   limited bitwidth
-   memory bandwidth
-   power consumption
-   area constraints

This project explores **precision as a tunable architectural
parameter**, allowing controlled **energy--accuracy tradeoffs**.

------------------------------------------------------------------------

# ⚙️ Current Development Flow

### 1️⃣ Baseline Architecture

The initial implementation is a **pure FP4 FFT processor**.

The following RTL modules were implemented:

-   complex multiplier
-   butterfly unit
-   address generation unit (AGU)
-   FFT core
-   top-level FFT controller

Simulation outputs were compared against an **FP32 NumPy FFT
reference**.

------------------------------------------------------------------------

### 2️⃣ Numerical Error Analysis

Large numerical deviations were initially observed.

Two hypotheses were investigated:

-   architectural issues (memory timing)
-   quantization noise from FP4 precision

After correcting memory timing issues, remaining error was confirmed to
be **quantization noise from reduced precision**.

------------------------------------------------------------------------

### 3️⃣ Precision Analysis

A Python evaluation framework was built to analyze multiple formats:

-   FP4 (E2M1)
-   FP4 (E1M2)
-   FP8 (E4M3)

Evaluation metrics include:

-   **SQNR**
-   **RMSE**
-   spectral similarity

Results showed **FP8 significantly improves dynamic range and numerical
fidelity** compared to FP4.

------------------------------------------------------------------------

### 4️⃣ Stage‑Wise Precision Sensitivity

Experiments revealed that **different FFT stages tolerate precision loss
differently**.

This led to the idea of a **mixed‑precision FFT pipeline**, where each
stage can independently use:

-   FP4
-   FP8

------------------------------------------------------------------------

# 🧬 Mixed‑Precision Architecture Idea

Each FFT stage can independently choose precision for:

-   multipliers
-   adders

This is encoded as a chromosome for optimization:

(mult_precision, add_precision)

Example encoding:

0 → FP4\
1 → FP8

For an N‑point FFT:

stages = log2(N)\
chromosome length = 2 × stages

Example:

FFT‑8 → 6 genes\
FFT‑16 → 8 genes\
FFT‑32 → 10 genes

------------------------------------------------------------------------

# 🏗 Project Structure

    .
    ├── verilog_sources
    │   Core RTL building blocks
    │
    ├── generated_designs
    │   Auto‑generated FFT cores and top modules
    │   produced by the template generator
    │
    ├── vivado_projects
    │   Synthesis runs
    │
    ├── reports
    │   Power and area reports
    │
    ├── sim
    │   Simulation files and test vectors
    │
    ├── results
    │   Optimization outputs
    │
    ├── fft_template_generator.py
    │   Generates FFT hardware for each chromosome
    │
    ├── objectiveEvaluationFFT.py
    │   Evaluates candidate architectures
    │
    ├── performance_evaluator.py
    │   Computes SQNR / MAE using simulation
    │
    ├── optimizationUtils.py
    │   Genetic operators for optimization
    │
    └── twiddle_factor_gen.py
        Generates twiddle factor tables

------------------------------------------------------------------------

# 🧩 RTL Modules

Core RTL components located in **verilog_sources/** include:

-   `adder.v`
-   `multiplier.v`
-   `butterfly.v`
-   `memory.v`
-   `agu.v`
-   `bit_reversal.v`
-   `twiddle_rom.v`
-   `precision_converter.v`
-   `mixed_precision_wrappers.v`

These modules form the building blocks of the FFT pipeline.

------------------------------------------------------------------------

# 🏭 Generated Designs

The script **fft_template_generator.py** automatically produces FFT
architectures.

Each candidate design generates:

-   a **core module**
-   a **top-level wrapper**

These are placed inside:

    generated_designs/

Example:

    fft_8_sol0_gen1.v
    fft_8_sol0_gen1_top.v

Each file corresponds to a **specific precision configuration produced
during optimization**.

------------------------------------------------------------------------

# 📊 Evaluation Pipeline

Each generated architecture goes through:

chromosome\
↓\
Verilog generation\
↓\
simulation\
↓\
Vivado synthesis\
↓\
power + area extraction\
↓\
SQNR evaluation

------------------------------------------------------------------------

# 🚧 Current Status

Implemented:

-   FP4 FFT architecture
-   precision analysis framework
-   automated hardware generation
-   synthesis‑based power/area evaluation
-   simulation‑based SQNR measurement

Next step:

🧬 **NSGA‑II based multi‑objective optimization (in progress)**

The optimization will search for **Pareto‑optimal mixed‑precision FFT
architectures** balancing:

-   power
-   area
-   numerical accuracy
