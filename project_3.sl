#!/bin/bash
#SBATCH --job-name=vrp_parallel     # Job name
#SBATCH --output=vrp_output_%j.log  # Log file (%j adds job ID)
#SBATCH --time=00:03:00             # Maximum run time (adjust as needed)
#SBATCH --nodes=16                   # Use one node
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH -A anakano_429

module load openmpi  # Load MPI module
module load gurobi/11.0.2
module load gcc/11.3.0
module load python/3.11.3

# Ensure Python can find user-installed packages
export PYTHONUSERBASE=$HOME/.local
export PYTHONPATH=$PYTHONUSERBASE/lib/python3.11/site-packages:$PYTHONPATH

# Loop over the desired number of workers
for workers in 1 4 16 16; do
  echo "Running with $workers workers..."
  mpirun -np $workers python main.py

  echo "Completed run with $workers workers"
  echo "================================="
done
