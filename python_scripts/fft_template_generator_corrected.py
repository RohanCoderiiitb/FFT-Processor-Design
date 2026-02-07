"""
FFT Template Generator
"""

import os
import math
import numpy as np


class FFTTemplateGeneratorFinal:
    def __init__(self, fft_size):
        """
        Initialize FFT template generator with user's twiddle ROM
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
        """Generate top-level FFT module using unified twiddle ROM"""
        fft_size = config['fft_size']
        num_stages = config['num_stages']
        
        code = f"""// Auto-generated Mixed-Precision FFT
// FFT Size: {fft_size}
// Uses unified twiddle ROM with runtime precision selection
// Total Butterflies: {config['total_butterflies']}

module mixed_fft_{fft_size} (
    input clk,
    input rst,
    input start,
    input [15:0] data_in_real [{fft_size-1}:0],
    input [15:0] data_in_imag [{fft_size-1}:0],
    output reg [15:0] data_out_real [{fft_size-1}:0],
    output reg [15:0] data_out_imag [{fft_size-1}:0],
    output reg done
);

    // Stage interconnects
"""
        # Generate stage interconnects
        for stage in range(num_stages + 1):
            code += f"    wire [15:0] stage{stage}_real [{fft_size-1}:0];\n"
            code += f"    wire [15:0] stage{stage}_imag [{fft_size-1}:0];\n"
        
        code += "\n    // Twiddle factor wires\n"
        code += f"    wire [15:0] twiddle [{fft_size-1}:0];\n\n"
        
        # Generate twiddle ROM instances (one per unique twiddle index)
        code += "    // Twiddle ROM instances (unified, runtime precision-selectable)\n"
        twiddle_indices = set()
        for stage_idx, stage in enumerate(config['stages']):
            group_size = 2 ** (stage_idx + 1)
            num_groups = fft_size // group_size
            butterflies_per_group = group_size // 2
            
            for group in range(num_groups):
                for bf in range(butterflies_per_group):
                    twiddle_idx = (bf * num_groups) % fft_size
                    twiddle_indices.add(twiddle_idx)
        
        # Note: We'll use per-butterfly precision for twiddle ROM
        # For simplicity, use multiplier precision for twiddle selection
        code += f"    // Note: Twiddle precision matches multiplier precision per butterfly\n\n"
        
        # Input assignment
        code += "    // Input assignment\n"
        for i in range(fft_size):
            code += f"    assign stage0_real[{i}] = data_in_real[{i}];\n"
            code += f"    assign stage0_imag[{i}] = data_in_imag[{i}];\n"
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
            code += f"            data_out_real[{i}] <= 16'h0;\n"
            code += f"            data_out_imag[{i}] <= 16'h0;\n"
        code += "        end else if (start) begin\n"
        for i in range(fft_size):
            code += f"            data_out_real[{i}] <= stage{num_stages}_real[{i}];\n"
            code += f"            data_out_imag[{i}] <= stage{num_stages}_imag[{i}];\n"
        code += "            done <= 1;\n"
        code += "        end\n"
        code += "    end\n\n"
        
        code += "endmodule\n"
        
        return code
    
    def _generate_stage_with_unified_twiddle(self, stage_config, fft_size, stage_num):
        """Generate a stage using unified twiddle ROM"""
        stage = stage_config['stage_num']
        
        code = f"    // ===== Stage {stage} =====\n"
        code += f"    // {len(stage_config['butterflies'])} butterflies in parallel\n\n"
        
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
                
                # Generate butterfly with specific precision
                code += f"    mixed_butterfly #(\n"
                code += f"        .MULT_PRECISION({mult_prec}),\n"
                code += f"        .ADD_PRECISION({add_prec})\n"
                code += f"    ) bf_s{stage}_g{group}_b{bf} (\n"
                code += f"        .A({{stage{stage}_real[{idx_a}], stage{stage}_imag[{idx_a}]}}),\n"
                code += f"        .B({{stage{stage}_real[{idx_b}], stage{stage}_imag[{idx_b}]}}),\n"
                code += f"        .W(twiddle_s{stage}_bf{butterfly_idx}),\n"
                code += f"        .X({{stage{stage+1}_real[{idx_a}], stage{stage+1}_imag[{idx_a}]}}),\n"
                code += f"        .Y({{stage{stage+1}_real[{idx_b}], stage{stage+1}_imag[{idx_b}]}})\n"
                code += f"    );\n\n"
                
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


def test_generator_with_unified_twiddle():
    """Test the FFT template generator with unified twiddle ROM"""
    print("Testing FFT Template Generator with Unified Twiddle ROM\n")
    
    # Test with 8-point FFT
    gen = FFTTemplateGeneratorFinal(fft_size=8)
    
    # Test all FP8 strategy
    all_fp8 = [1] * gen.get_chromosome_length()
    print("\n--- All FP8 Strategy ---")
    gen.print_chromosome_analysis(all_fp8)
    
    output_file = "test_fft_8_unified_twiddle.v"
    gen.generate_verilog(all_fp8, output_file)
    print(f"\n✓ Generated Verilog: {output_file}")
    print("\nCheck the file - it should use twiddle_factor_unified module!")


if __name__ == "__main__":
    test_generator_with_unified_twiddle()