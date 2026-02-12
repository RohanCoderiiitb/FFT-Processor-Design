"""
FFT Template Generator - Updated for 24-bit Unified Memory Format
Format: [23:16] FP8 Real, [15:8] FP8 Imag, [7:4] FP4 Real, [3:0] FP4 Imag
"""

import os
import math
import numpy as np


class FFTTemplateGenerator:
    def __init__(self, fft_size):
        """
        Initialize FFT template generator with unified 24-bit twiddle ROM
        Args:
            fft_size: FFT size (must be power of 2, range: 2 to 1024)
        """
        self.fft_size = fft_size
        self.num_stages = int(math.log2(fft_size))
        self.butterflies_per_stage = fft_size // 2
        self.total_butterflies = self.butterflies_per_stage * self.num_stages
        
        print(f"FFT-{fft_size} Configuration:")
        print(f"  Stages: {self.num_stages}")
        print(f"  Butterflies/stage: {self.butterflies_per_stage}")
        print(f"  Total butterflies: {self.total_butterflies}")
        print(f"  Chromosome length: {2 * self.total_butterflies}")
        print(f"  Memory format: 24-bit unified (FP8 + FP4)")
    
    def get_chromosome_length(self):
        """Return the required chromosome length"""
        return 2 * self.total_butterflies
    
    def chromosome_to_config(self, chromosome):
        """Convert NSGA-II chromosome to precision configuration"""
        config = {
            'fft_size': self.fft_size,
            'num_stages': self.num_stages,
            'butterflies_per_stage': self.butterflies_per_stage,
            'total_butterflies': self.total_butterflies,
            'stages': []
        }
        
        butterfly_global_idx = 0
        
        for stage in range(self.num_stages):
            stage_config = {
                'stage_num': stage,
                'butterflies': []
            }
            
            for bf_in_stage in range(self.butterflies_per_stage):
                chrom_idx = butterfly_global_idx * 2
                
                mult_prec = chromosome[chrom_idx] if chrom_idx < len(chromosome) else 0
                add_prec = chromosome[chrom_idx + 1] if chrom_idx + 1 < len(chromosome) else 0
                
                butterfly_config = {
                    'butterfly_id': bf_in_stage,
                    'global_butterfly_id': butterfly_global_idx,
                    'mult_precision': mult_prec,
                    'add_precision': add_prec
                }
                
                stage_config['butterflies'].append(butterfly_config)
                butterfly_global_idx += 1
            
            config['stages'].append(stage_config)
        
        return config
    
    def generate_verilog(self, chromosome, output_path):
        """Generate complete Verilog FFT design from chromosome"""
        config = self.chromosome_to_config(chromosome)
        verilog_code = self._generate_fft_top(config)
        
        with open(output_path, 'w') as f:
            f.write(verilog_code)
        
        return output_path
    
    def _generate_fft_top(self, config):
        """Generate top-level FFT module using unified 24-bit twiddle ROM"""
        fft_size = config['fft_size']
        num_stages = config['num_stages']
        
        code = f"""// Auto-generated Mixed-Precision FFT
// FFT Size: {fft_size}
// Memory Format: 24-bit unified ([23:16] FP8 Real, [15:8] FP8 Imag, [7:4] FP4 Real, [3:0] FP4 Imag)
// Uses unified twiddle ROM with runtime precision selection
// Total Butterflies: {config['total_butterflies']}

module mixed_fft_{fft_size} (
    input clk,
    input rst,
    input start,
    input [23:0] data_in [{fft_size-1}:0],  // 24-bit unified format input
    output reg [23:0] data_out [{fft_size-1}:0],  // 24-bit unified format output
    output reg done
);

    // Stage interconnects (24-bit unified format)
"""
        # Generate stage interconnects
        for stage in range(num_stages + 1):
            code += f"    wire [23:0] stage{stage} [{fft_size-1}:0];\n"
        
        code += "\n"
        
        # Input assignment
        code += "    // Input assignment\n"
        for i in range(fft_size):
            code += f"    assign stage0[{i}] = data_in[{i}];\n"
        code += "\n"
        
        # Generate each stage with butterflies
        for stage_idx, stage in enumerate(config['stages']):
            code += self._generate_stage_with_unified_twiddle(stage, fft_size, stage_idx)
        
        # Output assignment
        code += "    // Output assignment\n"
        code += "    always @(posedge clk) begin\n"
        code += "        if (rst) begin\n"
        code += "            done <= 0;\n"
        for i in range(fft_size):
            code += f"            data_out[{i}] <= 24'h0;\n"
        code += "        end else if (start) begin\n"
        for i in range(fft_size):
            code += f"            data_out[{i}] <= stage{num_stages}[{i}];\n"
        code += "            done <= 1;\n"
        code += "        end\n"
        code += "    end\n\n"
        
        code += "endmodule\n"
        
        return code
    
    def _generate_stage_with_unified_twiddle(self, stage_config, fft_size, stage_num):
        """Generate a stage using unified 24-bit twiddle ROM"""
        stage = stage_config['stage_num']
        
        code = f"    // ===== Stage {stage} =====\n"
        code += f"    // {len(stage_config['butterflies'])} butterflies in parallel\n"
        code += f"    // Using 24-bit unified memory format\n\n"
        
        # Calculate butterfly indices for Radix-2 DIT FFT
        group_size = 2 ** (stage + 1)
        num_groups = fft_size // group_size
        butterflies_per_group = group_size // 2
        
        butterfly_idx = 0
        for group in range(num_groups):
            for bf in range(butterflies_per_group):
                bf_config = stage_config['butterflies'][butterfly_idx]
                mult_prec = bf_config['mult_precision']
                add_prec = bf_config['add_precision']
                
                idx_a = group * group_size + bf
                idx_b = idx_a + butterflies_per_group
                twiddle_k = bf * num_groups
                
                mult_type = "FP8" if mult_prec == 1 else "FP4"
                add_type = "FP8" if add_prec == 1 else "FP4"
                
                # Generate twiddle ROM instance for this butterfly
                code += f"    // Butterfly {butterfly_idx}: Mult={mult_type}, Add={add_type}\n"
                code += f"    wire [15:0] twiddle_s{stage}_bf{butterfly_idx};\n"
                code += f"    twiddle_factor_unified #(\n"
                code += f"        .MAX_N(1024),\n"
                code += f"        .PRECISION({mult_prec})  // Use multiplier precision for twiddle\n"
                code += f"    ) twiddle_rom_s{stage}_bf{butterfly_idx} (\n"
                code += f"        .k({twiddle_k}),\n"
                code += f"        .n({fft_size}),\n"
                code += f"        .twiddle_out(twiddle_s{stage}_bf{butterfly_idx})\n"
                code += f"    );\n\n"
                
                # Wire declarations for precision selection
                code += f"    // Precision-selected data for butterfly {butterfly_idx}\n"
                code += f"    wire [15:0] bf_s{stage}_b{butterfly_idx}_A;\n"
                code += f"    wire [15:0] bf_s{stage}_b{butterfly_idx}_B;\n"
                code += f"    wire [15:0] bf_s{stage}_b{butterfly_idx}_X;\n"
                code += f"    wire [15:0] bf_s{stage}_b{butterfly_idx}_Y;\n\n"
                
                # Input precision extraction
                code += f"    // Extract input data based on multiplier precision\n"
                code += f"    assign bf_s{stage}_b{butterfly_idx}_A = ({mult_prec} == 1) ? \n"
                code += f"        stage{stage}[{idx_a}][23:8] :  // FP8\n"
                code += f"        {{8'h00, stage{stage}[{idx_a}][7:0]}};  // FP4\n"
                code += f"    assign bf_s{stage}_b{butterfly_idx}_B = ({mult_prec} == 1) ? \n"
                code += f"        stage{stage}[{idx_b}][23:8] :  // FP8\n"
                code += f"        {{8'h00, stage{stage}[{idx_b}][7:0]}};  // FP4\n\n"
                
                # Generate butterfly with specific precision
                code += f"    butterfly_wrapper #(\n"
                code += f"        .MULT_PRECISION({mult_prec}),\n"
                code += f"        .ADD_PRECISION({add_prec})\n"
                code += f"    ) bf_s{stage}_g{group}_b{bf} (\n"
                code += f"        .A(bf_s{stage}_b{butterfly_idx}_A),\n"
                code += f"        .B(bf_s{stage}_b{butterfly_idx}_B),\n"
                code += f"        .W(twiddle_s{stage}_bf{butterfly_idx}),\n"
                code += f"        .X(bf_s{stage}_b{butterfly_idx}_X),\n"
                code += f"        .Y(bf_s{stage}_b{butterfly_idx}_Y)\n"
                code += f"    );\n\n"
                
                # Output precision packing
                code += f"    // Pack output data based on add precision\n"
                code += f"    assign stage{stage+1}[{idx_a}] = ({add_prec} == 1) ? \n"
                code += f"        {{bf_s{stage}_b{butterfly_idx}_X, 8'h00}} :  // FP8 result in upper bits\n"
                code += f"        {{16'h0000, bf_s{stage}_b{butterfly_idx}_X[7:0]}};  // FP4 result in lower bits\n"
                code += f"    assign stage{stage+1}[{idx_b}] = ({add_prec} == 1) ? \n"
                code += f"        {{bf_s{stage}_b{butterfly_idx}_Y, 8'h00}} :  // FP8 result in upper bits\n"
                code += f"        {{16'h0000, bf_s{stage}_b{butterfly_idx}_Y[7:0]}};  // FP4 result in lower bits\n\n"
                
                butterfly_idx += 1
        
        return code
    
    def analyze_chromosome_statistics(self, chromosome):
        """Analyze chromosome precision distribution"""
        config = self.chromosome_to_config(chromosome)
        
        stats = {
            'total_butterflies': self.total_butterflies,
            'fp4_mult': 0,
            'fp8_mult': 0,
            'fp4_add': 0,
            'fp8_add': 0,
            'stage_stats': []
        }
        
        for stage in config['stages']:
            stage_stat = {
                'stage': stage['stage_num'],
                'fp4_mult': 0,
                'fp8_mult': 0,
                'fp4_add': 0,
                'fp8_add': 0
            }
            
            for bf in stage['butterflies']:
                if bf['mult_precision'] == 0:
                    stats['fp4_mult'] += 1
                    stage_stat['fp4_mult'] += 1
                else:
                    stats['fp8_mult'] += 1
                    stage_stat['fp8_mult'] += 1
                
                if bf['add_precision'] == 0:
                    stats['fp4_add'] += 1
                    stage_stat['fp4_add'] += 1
                else:
                    stats['fp8_add'] += 1
                    stage_stat['fp8_add'] += 1
            
            stats['stage_stats'].append(stage_stat)
        
        return stats
    
    def print_chromosome_analysis(self, chromosome):
        """Print detailed chromosome analysis"""
        stats = self.analyze_chromosome_statistics(chromosome)
        
        print(f"\n{'='*60}")
        print(f"Chromosome Analysis for {self.fft_size}-point FFT")
        print(f"{'='*60}")
        print(f"Total Butterflies: {stats['total_butterflies']}")
        print(f"\nOverall Precision Distribution:")
        print(f"  Multipliers: {stats['fp4_mult']} FP4 ({stats['fp4_mult']/stats['total_butterflies']*100:.1f}%), "
              f"{stats['fp8_mult']} FP8 ({stats['fp8_mult']/stats['total_butterflies']*100:.1f}%)")
        print(f"  Adders:      {stats['fp4_add']} FP4 ({stats['fp4_add']/stats['total_butterflies']*100:.1f}%), "
              f"{stats['fp8_add']} FP8 ({stats['fp8_add']/stats['total_butterflies']*100:.1f}%)")
        
        print(f"\nPer-Stage Breakdown:")
        print(f"{'Stage':<8} {'FP4 Mult':<12} {'FP8 Mult':<12} {'FP4 Add':<12} {'FP8 Add':<12}")
        print('-' * 60)
        for stage_stat in stats['stage_stats']:
            print(f"{stage_stat['stage']:<8} "
                  f"{stage_stat['fp4_mult']:<12} "
                  f"{stage_stat['fp8_mult']:<12} "
                  f"{stage_stat['fp4_add']:<12} "
                  f"{stage_stat['fp8_add']:<12}")


def test_generator_with_unified_24bit():
    """Test the FFT template generator with unified 24-bit ROM"""
    print("Testing FFT Template Generator with Unified 24-bit Memory Format\n")
    
    # Test with 8-point FFT
    gen = FFTTemplateGenerator(fft_size=8)
    
    # Test all FP8 strategy
    all_fp8 = [1] * gen.get_chromosome_length()
    print("\n--- All FP8 Strategy ---")
    gen.print_chromosome_analysis(all_fp8)
    
    output_file = "test_fft_8_unified_24bit.v"
    gen.generate_verilog(all_fp8, output_file)
    print(f"\n✓ Generated Verilog: {output_file}")
    print("\nFeatures:")
    print("  - 24-bit unified memory format")
    print("  - Runtime precision selection")
    print("  - FP8 in bits [23:8], FP4 in bits [7:0]")
    
    # Test mixed precision strategy
    print("\n" + "="*60)
    mixed = [0, 1] * (gen.get_chromosome_length() // 2)
    print("\n--- Mixed Precision Strategy (alternating FP4/FP8) ---")
    gen.print_chromosome_analysis(mixed)
    
    output_file_mixed = "test_fft_8_mixed_24bit.v"
    gen.generate_verilog(mixed, output_file_mixed)
    print(f"\n✓ Generated Verilog: {output_file_mixed}")


if __name__ == "__main__":
    test_generator_with_unified_24bit()