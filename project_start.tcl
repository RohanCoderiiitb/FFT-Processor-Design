# 1. Create a project in a separate workspace folder to keep the repo clean
set project_name "My_FFT_Hardware"
set project_dir "./Vivado_Workspace"
create_project $project_name $project_dir -part xc7a35tcpg236-1 -force

# 2. Add your existing Verilog sources
add_files [glob ./verilog_sources/*.v]

# 4. Set a module as 'Top' for analysis (since you don't have a top-level yet)
set_property top multiplier [current_fileset]
update_compile_order -fileset sources_1

puts "--- Project Created: You can now run Synthesis for metrics ---"