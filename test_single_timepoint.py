import cuml
from cuml.cluster import AgglomerativeClustering
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.stats import zscore
from collections import Counter
import pandas as pd
import cupy as cp
import time

# Load data from CSV file
data = pd.read_csv('data.csv')

# Test with original parameters
start_timepoint = 200
current_start_timepoint = start_timepoint
end_timepoint = current_start_timepoint + 2001

print(f"Testing single timepoint analysis...")
print(f"Start timepoint: {start_timepoint}")
print(f"End timepoint: {end_timepoint}")

start_time = time.time()

# Pivot the data to create the first table with Closing values
print("Creating closing table...")
closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[current_start_timepoint:end_timepoint]

# Extract variable names from closing_table
variable_names = closing_table.columns.to_numpy()
print(f"Original variable count: {len(variable_names)}")

# Pivot the data to create the second table with Volume values
print("Creating volume table...")
volume_table = data.pivot_table(index='Date', columns='Symbol', values='Volume', aggfunc='first').iloc[end_timepoint-10:end_timepoint]

# Remove the Date column
closing_table.reset_index(drop=True, inplace=True)
volume_table.reset_index(drop=True, inplace=True)

# Replace NaN values with 0
closing_table = closing_table.fillna(0)
volume_table = volume_table.fillna(0)

# Transpose the tables
closing_table = closing_table.T
volume_table = volume_table.T

# Convert closing_table and volume_table to numpy arrays
closing_table = closing_table.to_numpy()
volume_table = volume_table.to_numpy()

# Print the shapes of the tables to verify
print("Closing table shape:", closing_table.shape)
print("Volume table shape:", volume_table.shape)

# Number of variables and time points
num_variables, num_time_points = closing_table.shape

# Normalize the first 1501 time points using z-scores
print("Normalizing data...")
means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)

# Avoid division by zero - replace zero std with small value
stds = np.where(stds == 0, 1e-8, stds)

normalized_data = np.copy(closing_table)
normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds

# Apply the same mean and std to the last 500 time points
normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds

# Remove variables containing non-finite elements
finite_mask = np.all(np.isfinite(normalized_data), axis=1)
print(f"Variables before finite filter: {normalized_data.shape[0]}")
normalized_data = normalized_data[finite_mask]
last_500_normalized_data = normalized_data[:, 1501:]

# Apply finite_mask to data and volume_data
closing_table = closing_table[finite_mask]
volume_table = volume_table[finite_mask]

# Apply finite_mask to variable names
variable_names = variable_names[finite_mask]

print(f"Variables after finite filter: {normalized_data.shape[0]}")
print("Generated data shape:", closing_table.shape)

# Extract the last 500 time points of the normalized data
last_500_normalized_data = normalized_data[:, 1501:]

# Perform hierarchical clustering on the normalized data for the first 1501 time points 
print("Performing clustering...")

# Use AgglomerativeClustering from cuml for hierarchical clustering
# Note: cuML only supports 'single' linkage currently
clustering_model = AgglomerativeClustering(n_clusters=10, linkage='single')
clusters = clustering_model.fit_predict(cp.asarray(normalized_data[:, :1501]))
clusters = cp.asnumpy(clusters)

# Count the number of variables in each cluster
cluster_counts = Counter(clusters)
print(f"Cluster counts: {dict(cluster_counts)}")

# Find clusters that contain at least 40 variables
large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]
print(f"Large clusters (>=40 members): {large_clusters}")

# Initialize a dictionary to store the variable names for each large cluster
cluster_variable_names = {}

for cluster in large_clusters:
    # Get indices of variables in the current large cluster
    cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
    
    # Extract variable names for the current cluster
    variable_names_in_cluster = variable_names[cluster_indices]
    
    # Store the variable names in the dictionary
    cluster_variable_names[cluster] = variable_names_in_cluster

# Get the indices of variables in the large clusters
large_cluster_indices = [i for i, cluster in enumerate(clusters) if cluster in large_clusters]

print("Normalized data created with shape:", normalized_data.shape)
print("Clusters created with shape:", clusters.shape)
print("Number of large clusters:", len(large_clusters))

# Initialize a dictionary to store the current state for each large cluster
cluster_current_state = {}

print("Analyzing cluster states...")
for cluster in large_clusters:
    # Get indices of variables in the current large cluster
    cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
    
    # Extract data for the current cluster
    cluster_data = last_500_normalized_data[cluster_indices, :]
    
    # Compute the mean at each time point for the current cluster
    cluster_mean = np.mean(cluster_data, axis=0)
    
    # Compute the standard deviation at each time point for the current cluster
    cluster_std = np.std(cluster_data, axis=0)
    
    # Calculate the difference between the normalized values and the mean
    difference = cluster_data - cluster_mean
    
    # Divide the difference by the standard deviation
    standardized_difference = difference / np.where(cluster_std == 0, 1e-8, cluster_std)
    
    # Compute the z-score for the standardized differences
    z_scores = zscore(standardized_difference, axis=1)
    
    # Extract the last value of the z-score for each member of the cluster
    current_state = z_scores[:, -1]
    
    # Store the current state in the dictionary
    cluster_current_state[cluster] = current_state
    
    print(f"Cluster {cluster}: {len(current_state)} members, state range: {current_state.min():.3f} to {current_state.max():.3f}")

# Find variables whose state is less than -3 and give them a label of Long
long_labels = {}
long_table = []

print("Finding Long signals (state < -3)...")
for cluster, states in cluster_current_state.items():
    long_indices = np.where(states < -3)[0]
    if len(long_indices) > 0:
        cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
        long_variable_names = variable_names[cluster_indices][long_indices]
        long_labels[cluster] = long_variable_names
        print(f"Cluster {cluster}: Found {len(long_indices)} Long signals")
        for name, state in zip(long_variable_names, states[long_indices]):
            long_table.append([name, state])

# Convert the long_table to a DataFrame
long_table_df = pd.DataFrame(long_table, columns=['Variable Name', 'State'])
print(f"Total Long signals before filtering: {len(long_table_df)}")

# Add 'Price' column to the long_table DataFrame
if not long_table_df.empty:
    long_table_df['Price'] = long_table_df['Variable Name'].apply(lambda name: closing_table[variable_names.tolist().index(name), -1])
    # Add 'Volume' column to the long_table DataFrame using the mean of the last 10 values in volume_data
    long_table_df['Volume'] = long_table_df['Variable Name'].apply(lambda name: np.mean(volume_table[variable_names.tolist().index(name), -10:]))

# Find variables whose state is greater than 3.4 and give them a label of Short
short_labels = {}
short_table = []

print("Finding Short signals (state > 3.4)...")
for cluster, states in cluster_current_state.items():
    short_indices = np.where(states > 3.4)[0]
    if len(short_indices) > 0:
        cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
        short_variable_names = variable_names[cluster_indices][short_indices]
        short_labels[cluster] = short_variable_names
        print(f"Cluster {cluster}: Found {len(short_indices)} Short signals")
        for name, state in zip(short_variable_names, states[short_indices]):
            short_table.append([name, state])

# Convert the short_table to a DataFrame
short_table_df = pd.DataFrame(short_table, columns=['Variable Name', 'State'])
print(f"Total Short signals before filtering: {len(short_table_df)}")

# Add 'Price' column to the short_table DataFrame
if not short_table_df.empty:
    short_table_df['Price'] = short_table_df['Variable Name'].apply(lambda name: closing_table[variable_names.tolist().index(name), -1])
    # Add 'Volume' column to the short_table DataFrame using the mean of the last 10 values in volume_data
    short_table_df['Volume'] = short_table_df['Variable Name'].apply(lambda name: np.mean(volume_table[variable_names.tolist().index(name), -10:]))

# Combine long_table_df and short_table_df into a single DataFrame
if not long_table_df.empty or not short_table_df.empty:
    combined_table_df = pd.concat([long_table_df, short_table_df], ignore_index=True)
    
    # Add 'Type' column to the combined_table_df
    combined_table_df['Type'] = combined_table_df['State'].apply(lambda state: 'Long' if state < 0 else 'Short')
    
    print(f"Total signals before volume/price filtering: {len(combined_table_df)}")
    
    # Keep rows in combined_table_df with Price > 0 and Volume > 100000
    filtered_combined_table_df = combined_table_df[(combined_table_df['Price'] > 0) & (combined_table_df['Volume'] > 100000)]
    
    print(f"Total signals after volume/price filtering: {len(filtered_combined_table_df)}")
    
    if not filtered_combined_table_df.empty:
        print("\nFinal signals found:")
        print(filtered_combined_table_df)
        
        # Save results for comparison
        filtered_combined_table_df.to_csv('single_timepoint_test_results.csv', index=False)
        print("\nResults saved to: single_timepoint_test_results.csv")
    else:
        print("No signals passed the volume/price filter")
else:
    print("No signals found at all")

end_time = time.time()
print(f"\nTotal computation time: {end_time - start_time:.2f} seconds")