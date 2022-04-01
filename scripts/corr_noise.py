"""
This is a sample simulation that does not represent any particular biological system. It is just a showcase 
of how create a Simulation object, add forces, and initialize the reporter. 

In this simulation, a simple polymer chain of 10,000 monomers is 
"""
import time
import numpy as np
import os, sys
import polychrom
from polychrom import simulation, starting_conformations, forces, forcekits
from polychrom.integrators import ActiveBrownianIntegrator, CorrelatedNoiseIntegrator
import openmm
from polychrom.hdf5_format import HDF5Reporter
from simtk import unit
from pathlib import Path

total_runs = 2500
runs_per_gpu = total_runs // 2

def run_sim(i, gpuid=None, timestep=170, ntimesteps=10000, blocksize=100):
    """ Run a single simulation on GPU i."""
    N=100
    density = 0.224
    r = (3 * N / (4 * 3.141592 * density)) ** (1/3)
    print(f"Radius of confinement: {r}")
    D = np.ones((N, 3))
    rhos = 0.5*np.ones((1, N))
    rhos[0, 0:20] = -0.5
    rhos[0, 20:40] = 0.0
    rhos[0, 60:80] = 0.0
    timestep = timestep 
    collision_rate = 2.0
    friction = collision_rate * (1.0/unit.picosecond)
    conlen = 1.0 * unit.nanometer
    mass = 100 * unit.amu
    temperature = 300
    kB = unit.BOLTZMANN_CONSTANT_kB * unit.AVOGADRO_CONSTANT_NA
    kT = kB * temperature * unit.kelvin
    particleD = unit.Quantity(D, kT/(friction * mass))
    integrator = CorrelatedNoiseIntegrator(timestep, collision_rate, particleD, rhos)
    if gpuid is None:
        gpuid = f"{i % 4}"
    traj = f"/net/dau/home/dkannan/simulations/corr_sameT/ensemble10000_100/run{i}"
    Path(traj).mkdir(parents=True, exist_ok=True)
    reporter = HDF5Reporter(folder=traj, max_data_length=100, overwrite=True)
    sim = simulation.Simulation(
        platform="CUDA", 
        integrator=integrator,
        timestep=timestep,
        temperature=temperature,
        GPU=gpuid,
        collision_rate=collision_rate,
        N=N,
        save_decimals=2,
        PBCbox=False,
        reporters=[reporter],
    )

    polymer = starting_conformations.grow_cubic(N, 5)
    sim.set_data(polymer, center=True)  # loads a polymer, puts a center of mass at zero
    sim.set_velocities(v=np.zeros((N,3)))
    sim.add_force(forces.spherical_confinement(sim, density=density, k=5.0))
    sim.add_force(
        forcekits.polymer_chains(
            sim,
            chains=[(0, None, False)],
            # By default the library assumes you have one polymer chain
            # If you want to make it a ring, or more than one chain, use self.setChains
            # self.setChains([(0,50,True),(50,None,False)]) will set a 50-monomer ring and a chain from monomer 50 to the end
            bond_force_func=forces.harmonic_bonds,
            bond_force_kwargs={
                "bondLength": 1.0,
                "bondWiggleDistance": 0.3,  # Bond distance will fluctuate +- 0.05 on average
            },
            angle_force_func=None,
            angle_force_kwargs={},
            nonbonded_force_func=forces.polynomial_repulsive,
            nonbonded_force_kwargs={
                "trunc": 3.0,  # this will let chains cross sometimes
                #'trunc':10.0, # this will resolve chain crossings and will not let chain cross anymore
            },
            except_bonds=True,
        )
    )
    tic = time.perf_counter()
    for _ in range(ntimesteps):  # Do 10 blocks
        sim.do_block(blocksize)  # Of 100 timesteps each. Data is saved automatically. 
    toc = time.perf_counter()
    print(f'Ran simulation in {(toc - tic):0.4f}s')
    sim.print_stats()  # In the end, print very simple statistics
    reporter.dump_data()  # always need to run in the end to dump the block cache to the disk


if __name__ == '__main__':
    #run 8 simulations, one on each gpu, for the same parameters
    #run_sim(1)
    for i in range(1, 1 + 2*runs_per_gpu, 2):
        run_sim(i, gpuid="3")
