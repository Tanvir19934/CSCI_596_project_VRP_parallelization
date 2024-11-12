from gurobipy import GRB, Model, quicksum
import pickle
from config import *
import time
from utils import ev_travel_cost, standalone_cost_degree_2
from mpi4py import MPI
import csv

def load_routes():
    filenames = ['data.pkl']
    # Dictionary to hold the loaded dataframes
    loaded_dataframes = {}
    # Loop through the filenames and load each dataframe
    for filename in filenames:
        with open(filename, 'rb') as file:
            loaded_dataframes[filename[:-4]] = pickle.load(file)  # Remove .pkl extension for key
    # Access the loaded dataframes
    if 'data' in loaded_dataframes:
        ev_routes = loaded_dataframes['data']
    else:
        raise KeyError("The key 'data' was not found in the loaded dataframes.")
    return ev_routes


def lp(route, standalone_cost_degree_2,N_whole):
    time.sleep(0.01) #just to see the difference more clearly. comment this line in actual run
    mdl = Model(f'lp{route}')
    mdl.Params.OutputFlag = 0
    N_lp = route[1:-1]
    V_lp = route[0:-1]
    C_route, _ = ev_travel_cost(route)
    immediate = {}
    for idx, i in enumerate(route):
        if i!=0:
            immediate[i]=route[idx+1]
    # Decision variables
    p = {}
    e_IR = {}
    e_S = {}

    e_BB = mdl.addVar(vtype=GRB.CONTINUOUS, name = "e_BB")
    for i in N_lp:
        p[i] = mdl.addVar(vtype=GRB.CONTINUOUS, name = f"p{i}")
        e_IR[i] = mdl.addVar(vtype=GRB.CONTINUOUS, name = f"e_IR{i}")
        e_S[i] = mdl.addVar(vtype=GRB.CONTINUOUS, name = f"e_S{i}")

    #IR
    mdl.addConstrs((p[i]<=a[i,0]*GV_cost*q[i]+a[i,0]*GV_cost+e_IR[i]) for i in N_lp)

    #BB
    mdl.addConstr(quicksum(p[i] for i in N_lp)+(quicksum(e_IR[i] for i in N_lp)) + (quicksum(e_S[i] for i in N_lp))+ e_BB == C_route)

    #Stability
    for i in N_lp:
        for j in N_whole:
            if i!=j:
                mdl.addConstr(p[i]<=standalone_cost_degree_2[i,j][i]+e_S[i],name="stability")

    #mdl.addConstrs((p[i]<=(a[(i,j)]/EV_velocity)*(gamma+gamma_l*q[i])*260*EV_cost) for i in N_lp for j in N_lp if i!=j and immediate[i]==j)
    mdl.addConstrs((p[i]<=(a[(i,0)]/EV_velocity)*(gamma+gamma_l*q[i])*260*EV_cost+(a[(i,0)]/EV_velocity)*(gamma+gamma_l*0)*260*EV_cost) for i in N_lp)



    mdl.setObjective(e_BB + (quicksum(e_IR[i] for i in N_lp)) + (quicksum(e_S[i] for i in N_lp)))


    #mdl.write("/Users/tanvirkaisar/Library/CloudStorage/OneDrive-UniversityofSouthernCalifornia/CVRP/Codes/coalition.lp")
    mdl.optimize()
    def get_vars(item):
       vars = [var for var in mdl.getVars() if f"{item}" in var.VarName]
       names = mdl.getAttr('VarName', vars)
       values = mdl.getAttr('X', vars)
       return dict(zip(names, values))
    
    p_result = get_vars('p')
    e_S_result = get_vars('e_S')
    e_BB_result = get_vars('e_BB')
    e_IR_result = get_vars('e_IR')

    return p_result,e_S_result,e_BB_result,e_IR_result,route

def parallel_lp():
    # Initialize MPI
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    # Load routes on the root process and scatter them
    if rank == 0:
        ev_routes = load_routes()
        chunks = [ev_routes[i::size] for i in range(size)]  # Divide routes evenly across processes
    else:
        chunks = None

    # Scatter the route chunks to all processes
    routes = comm.scatter(chunks, root=0)

    # Each process processes its chunk of routes
    local_results = []
    for route in routes:
        result = lp(route, standalone_cost_degree_2, N)
        local_results.append(result)

    # Gather results at the root process
    all_results = comm.gather(local_results, root=0)

    if rank == 0:
        # Combine results from all processes
        p_result_dict, e_S_result_dict = {}, {}
        e_BB_result_dict, e_IR_result_dict = {}, {}
        total_p, total_S, total_IR, total_BB, total_ev_cost = 0, 0, 0, 0, 0

        for process_results in all_results:
            for p_result, e_S_result, e_BB_result, e_IR_result, route in process_results:
                # Store the results
                p_result_dict.update(p_result)
                e_S_result_dict.update(e_S_result)
                e_BB_result_dict.update(e_BB_result)
                e_IR_result_dict.update(e_IR_result)

                # Aggregate totals
                total_p += sum(p_result.values())
                total_S += sum(e_S_result.values())
                total_IR += sum(e_IR_result.values())
                total_BB += sum(e_BB_result.values())
                ev_cost, _ = ev_travel_cost(route)
                total_ev_cost += ev_cost

        #print(f"Total payment = {total_p, total_ev_cost}")
        #print(f"Total stability = {total_S}")
        #print(f"Total IR = {total_IR}")
        #print(f"Total BB = {total_BB}")
        #print(f"Total subsidy = {total_BB + total_IR + total_S}")
        total_subsidy = total_BB + total_IR + total_S
        # Return results only from the root process
        return size, total_subsidy, rank

    else:
        # Non-root processes return none values to avoid NoneType errors
        return None, None, None

if __name__ == "__main__":
    start_time = time.perf_counter()
    size, total_subsidy, rank = parallel_lp()
    end_time = time.perf_counter()
    execution_time = end_time - start_time

    if rank == 0:
        # Write results to CSV in append mode
        with open(f'results{n}.csv', 'a', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)

            # Write header only if the file is empty
            if csvfile.tell() == 0:
                csv_writer.writerow(['num_processor', 'Total Subsidy', 'Execution Time (seconds)'])

            # Write the results for the current run
            csv_writer.writerow([size, total_subsidy, execution_time])

        print(f"Execution time = {execution_time} seconds")