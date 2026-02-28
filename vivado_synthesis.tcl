# vivado_synthesis.tcl
# Template called by Python objectiveEvaluationFFT.py
#
# Arguments (passed via -tclargs):
#   1  design_name   – unique run identifier, e.g. fft_8_sol3_gen2
#   2  csv_output    – absolute path for the metrics CSV
#   3  clock_period  – target clock period in ns
#   4  core_file     – absolute path to the generated per-solution core .v
#   5  top_file      – absolute path to the shared top .v
#   6  verilog_dir   – directory containing the base library sources (adder.v, etc.)

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
set design_name  [lindex $argv 0]
set csv_output   [lindex $argv 1]
set clock_period [lindex $argv 2]
set core_file    [lindex $argv 3]
set top_file     [lindex $argv 4]
set verilog_dir  [lindex $argv 5]

set fft_size     [lindex [split $design_name "_"] 1]
# Top module name matches the generated file: <design_name>_top
set top_module   "${design_name}_top"

puts "============================================================"
puts " Vivado synthesis: $design_name"
puts "   Core file : $core_file"
puts "   Top  file : $top_file"
puts "   Lib  dir  : $verilog_dir"
puts "   Top module: $top_module"
puts "   CSV output: $csv_output"
puts "============================================================"

# ---------------------------------------------------------------------------
# Create in-memory project (no disk project, faster)
# ---------------------------------------------------------------------------
set project_dir "./vivado_projects/${design_name}"
create_project -in_memory -part xc7a35tcpg236-1

# ---------------------------------------------------------------------------
# Add source files
# ---------------------------------------------------------------------------
# 1. Base library (shared arithmetic / memory / AGU / twiddle / bit-reversal)
add_files -norecurse [glob ${verilog_dir}/*.v]

# 2. Per-solution generated core (overrides any same-named file in verilog_dir)
add_files -norecurse $core_file

# 3. Shared top wrapper for this FFT size
add_files -norecurse $top_file

# Set include path in case any file uses `include
set_property include_dirs $verilog_dir [current_fileset]

# ---------------------------------------------------------------------------
# Set elaboration top
# ---------------------------------------------------------------------------
set_property top $top_module [current_fileset]
update_compile_order -fileset sources_1

# ---------------------------------------------------------------------------
# Synthesis run
# ---------------------------------------------------------------------------
synth_design \
    -top        $top_module \
    -part       xc7a35tcpg236-1 \
    -mode       out_of_context

# ---------------------------------------------------------------------------
# Timing constraint (for power estimation)
# ---------------------------------------------------------------------------
create_clock -period $clock_period -name clk [get_ports clk]

# Run implementation-lite (opt + power analysis only, skip place & route)
opt_design

# ---------------------------------------------------------------------------
# Extract metrics
# ---------------------------------------------------------------------------

# --- Area ---
set lut_count 0
catch {
    set util_rpt [report_utilization -return_string]
    foreach line [split $util_rpt "\n"] {
        if {[regexp {^\|\s*LUT\s+\|\s+(\d+)\s+\|} $line match val]} {
            set lut_count [string trim $val]
            break
        }
        # Vivado 2021+ format
        if {[regexp {CLB LUTs\s*\|\s*(\d+)} $line match val]} {
            set lut_count [string trim $val]
            break
        }
    }
}

# --- Power ---
set total_power 0.0
catch {
    report_power -file /tmp/${design_name}_power.rpt
    set fp [open /tmp/${design_name}_power.rpt r]
    set power_data [read $fp]
    close $fp
    foreach line [split $power_data "\n"] {
        if {[regexp {Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)} $line match val]} {
            set total_power [string trim $val]
            break
        }
        # alternate format
        if {[regexp {\|\s*Total\s*\|\s*([0-9.]+)\s*\|} $line match val]} {
            set total_power [string trim $val]
            break
        }
    }
}

# --- Timing (worst negative slack) ---
set wns 0.0
catch {
    set timing_rpt [report_timing_summary -return_string]
    foreach line [split $timing_rpt "\n"] {
        if {[regexp {WNS\(ns\)\s+TNS\(ns\).*\n\s+([-0-9.]+)} $timing_rpt match val]} {
            set wns $val
            break
        }
    }
}

# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------
set csv_dir [file dirname $csv_output]
file mkdir $csv_dir

set fp [open $csv_output w]
puts $fp "Metric,Value"
puts $fp "design_name,$design_name"
puts $fp "top_module,$top_module"
puts $fp "lut_count,$lut_count"
puts $fp "total_power_w,$total_power"
puts $fp "wns_ns,$wns"
puts $fp "clock_period_ns,$clock_period"
close $fp

puts "------------------------------------------------------------"
puts " Synthesis complete for $design_name"
puts "   LUTs  : $lut_count"
puts "   Power : $total_power W"
puts "   WNS   : $wns ns"
puts "   CSV   : $csv_output"
puts "------------------------------------------------------------"g