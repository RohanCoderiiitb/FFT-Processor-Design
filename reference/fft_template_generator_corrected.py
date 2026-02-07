"""
FFT Template Generator for Mixed-Precision Optimization
CORRECTED VERSION: Per-butterfly precision control

For N-point FFT:
- Stages: log₂(N)
- Butterflies per stage: N/2
- Total butterflies: (N/2) × log₂(N)
- Decision variables: 2 × (N/2) × log₂(N)  [mult_prec, add_prec per butterfly]
"""

import os
import math
import numpy as np


class FFTTemplateGeneratorPerButterfly:
    def __init__(self, fft_size):
        """
        Initialize FFT template generator with per-butterfly precision
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
        # 2 decisions per butterfly: multiplier precision, adder precision
        return 2 * self.total_butterflies
    
    def chromosome_to_config(self, chromosome):
        """
        Convert NSGA-II chromosome to precision configuration
        
        Args:
            chromosome: List/array of integers representing precision choices
                       Length: 2 × (N/2) × log₂(N)
                       Format: [bf0_mult, bf0_add, bf1_mult, bf1_add, ...]
                       Each element: 0=FP4, 1=FP8
        
        Returns:
            dict with stage-wise and butterfly-wise precision config
        """
        config = {
            'fft_size': self.fft_size,
            'num_stages': self.num_stages,
            'butterflies_per_stage': self.butterflies_per_stage,
            'total_butterflies': self.total_butterflies,
            'stages': []
        }
        
        # Decode chromosome: sequentially assign to butterflies
        butterfly_global_idx = 0
        
        for stage in range(self.num_stages):
            stage_config = {
                'stage_num': stage,
                'butterflies': []
            }
            
            # Each stage has N/2 butterflies operating in parallel
            for bf_in_stage in range(self.butterflies_per_stage):
                chrom_idx = butterfly_global_idx * 2
                
                # Get precision for this butterfly
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
        """
        Generate complete Verilog FFT design from chromosome
        
        Args:
            chromosome: NSGA-II chromosome encoding precision choices
            output_path: Path to save generated Verilog file
        """
        config = self.chromosome_to_config(chromosome)
        verilog_code = self._generate_fft_top(config)
        
        with open(output_path, 'w') as f:
            f.write(verilog_code)
        
        return output_path
    
    def _generate_fft_top(self, config):
        """Generate top-level FFT module with all butterflies"""
        fft_size = config['fft_size']
        num_stages = config['num_stages']
        
        code = f"""// Auto-generated Mixed-Precision FFT
// FFT Size: {fft_size}
// Number of Stages: {num_stages}
// Butterflies per Stage: {config['butterflies_per_stage']}
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

"""
        # Generate stage interconnects
        for stage in range(num_stages + 1):
            code += f"    wire [15:0] stage{stage}_real [{fft_size-1}:0];\n"
            code += f"    wire [15:0] stage{stage}_imag [{fft_size-1}:0];\n"
        
        code += "\n"
        
        # Input assignment
        code += "    // Input assignment\n"
        for i in range(fft_size):
            code += f"    assign stage0_real[{i}] = data_in_real[{i}];\n"
            code += f"    assign stage0_imag[{i}] = data_in_imag[{i}];\n"
        code += "\n"
        
        # Generate each stage with all parallel butterflies
        for stage_idx, stage in enumerate(config['stages']):
            code += self._generate_stage(stage, fft_size, stage_idx)
        
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
    
    def _generate_stage(self, stage_config, fft_size, stage_num):
        """Generate a single FFT stage with all parallel butterflies"""
        stage = stage_config['stage_num']
        
        code = f"    // ===== Stage {stage} =====\n"
        code += f"    // {len(stage_config['butterflies'])} butterflies operating in parallel\n\n"
        
        # Calculate butterfly indices for Radix-2 DIT FFT
        group_size = 2 ** (stage + 1)
        num_groups = fft_size // group_size
        butterflies_per_group = group_size // 2
        
        butterfly_idx = 0
        for group in range(num_groups):
            for bf in range(butterflies_per_group):
                # Get precision for this specific butterfly
                bf_config = stage_config['butterflies'][butterfly_idx]
                mult_prec = bf_config['mult_precision']
                add_prec = bf_config['add_precision']
                
                # Calculate data indices for Radix-2 DIT
                idx_a = group * group_size + bf
                idx_b = idx_a + butterflies_per_group
                
                # Twiddle factor index
                twiddle_idx = (bf * num_groups) % fft_size
                
                # Generate butterfly with specific precision
                mult_type = "FP8" if mult_prec == 1 else "FP4"
                add_type = "FP8" if add_prec == 1 else "FP4"
                
                code += f"    // Butterfly {butterfly_idx}: Mult={mult_type}, Add={add_type}\n"
                code += f"    mixed_butterfly #(\n"
                code += f"        .MULT_PRECISION({mult_prec}),\n"
                code += f"        .ADD_PRECISION({add_prec})\n"
                code += f"    ) bf_s{stage}_g{group}_b{bf} (\n"
                code += f"        .A({{stage{stage}_real[{idx_a}], stage{stage}_imag[{idx_a}]}}),\n"
                code += f"        .B({{stage{stage}_real[{idx_b}], stage{stage}_imag[{idx_b}]}}),\n"
                code += f"        .W(twiddle_{fft_size}[{twiddle_idx}]),\n"
                code += f"        .X({{stage{stage+1}_real[{idx_a}], stage{stage+1}_imag[{idx_a}]}}),\n"
                code += f"        .Y({{stage{stage+1}_real[{idx_b}], stage{stage+1}_imag[{idx_b}]}})\n"
                code += f"    );\n\n"
                
                butterfly_idx += 1
        
        return code
    
    def analyze_chromosome_statistics(self, chromosome):
        """
        Analyze a chromosome to show precision distribution
        Returns statistics about FP4 vs FP8 usage
        """
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
        """Print detailed analysis of chromosome"""
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


def test_generator():
    """Test the corrected FFT template generator"""
    print("Testing Per-Butterfly Precision FFT Generator\n")
    
    # Test with 8-point FFT
    gen = FFTTemplateGeneratorPerButterfly(fft_size=8)
    
    # Example chromosome: random precision for each butterfly
    # 8-point FFT: 3 stages × 4 butterflies = 12 butterflies
    # Chromosome length: 12 × 2 = 24 decisions
    
    # Strategy 1: All FP4 (minimum power)
    all_fp4 = [0] * gen.get_chromosome_length()
    print("\n--- Strategy 1: All FP4 ---")
    gen.print_chromosome_analysis(all_fp4)
    
    # Strategy 2: All FP8 (maximum performance)
    all_fp8 = [1] * gen.get_chromosome_length()
    print("\n--- Strategy 2: All FP8 ---")
    gen.print_chromosome_analysis(all_fp8)
    
    # Strategy 3: Progressive precision (FP4 early stages, FP8 later stages)
    progressive = []
    for stage in range(gen.num_stages):
        # Later stages use higher precision
        if stage < gen.num_stages // 2:
            stage_prec = [0, 0]  # FP4 mult, FP4 add
        else:
            stage_prec = [1, 1]  # FP8 mult, FP8 add
        
        for bf in range(gen.butterflies_per_stage):
            progressive.extend(stage_prec)
    
    print("\n--- Strategy 3: Progressive Precision ---")
    gen.print_chromosome_analysis(progressive)
    
    # Generate Verilog for progressive strategy
    output_file = "test_fft_8_progressive.v"
    gen.generate_verilog(progressive, output_file)
    print(f"\n✓ Generated Verilog: {output_file}")
    
    # Test larger FFT
    print("\n" + "="*60)
    gen_large = FFTTemplateGeneratorPerButterfly(fft_size=64)
    
    # For 64-point FFT: 6 stages × 32 butterflies = 192 butterflies
    # Chromosome length: 192 × 2 = 384 decisions
    print(f"\nChromosome length for 64-point FFT: {gen_large.get_chromosome_length()}")


if __name__ == "__main__":
    test_generator()
