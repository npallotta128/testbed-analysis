
import cuml
from cuml.cluster import AgglomerativeClustering
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.stats import zscore
from collections import Counter
import pandas as pd
import cupy as cp

# Load data from CSV file
data = pd.read_csv('/mnt/d/data.csv')

# Define the starting timepoint
start_timepoint = 200

# Initialize an empty DataFrame to store all results
all_filtered_combined_table_df = pd.DataFrame()

# Iterate over the next 250 timepoints
for i in range(1):
    current_start_timepoint = start_timepoint + i
    end_timepoint = current_start_timepoint + 2001

    # Print the end timepoint
    print("End timepoint:", end_timepoint)

    # Pivot the data to create the first table with Closing values
    closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[current_start_timepoint:end_timepoint]

    # Extract variable names from closing_table
    variable_names = closing_table.columns.to_numpy()

    # Pivot the data to create the second table with Volume values
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
    means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
    stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)

    normalized_data = np.copy(closing_table)
    normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds

    # Apply the same mean and std to the last 500 time points
    normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds

    # Remove variables containing non-finite elements
    finite_mask = np.all(np.isfinite(normalized_data), axis=1)
    normalized_data = normalized_data[finite_mask]
    last_500_normalized_data = normalized_data[:, 1501:]

    # Apply finite_mask to data and volume_data
    closing_table = closing_table[finite_mask]
    volume_table = volume_table[finite_mask]

    # Apply finite_mask to variable names
    variable_names = variable_names[finite_mask]

    # Print the shape of the generated data to verify
    print("Generated data shape:", closing_table.shape)

    # Extract the last 500 time points of the normalized data
    last_500_normalized_data = normalized_data[:, 1501:]


    # Perform hierarchical clustering on the normalized data for the first 1501 time points 
    

    # Use AgglomerativeClustering from cuml for hierarchical clustering
    clustering_model = AgglomerativeClustering(n_clusters=10, linkage='ward')
    clusters = clustering_model.fit_predict(cp.asarray(normalized_data[:, :1501]))
    clusters = cp.asnumpy(clusters)


    # Count the number of variables in each cluster
    cluster_counts = Counter(clusters)

    # Find clusters that contain at least 40 variables
    large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]

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
        standardized_difference = difference / cluster_std
        
        # Compute the z-score for the standardized differences
        z_scores = zscore(standardized_difference, axis=1)
        
        # Extract the last value of the z-score for each member of the cluster
        current_state = z_scores[:, -1]
        
        # Store the current state in the dictionary
        cluster_current_state[cluster] = current_state

    # Find variables whose state is less than -3 and give them a label of Long
    long_labels = {}
    long_table = []

    for cluster, states in cluster_current_state.items():
        long_indices = np.where(states < -3)[0]
        cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
        long_variable_names = variable_names[cluster_indices][long_indices]
        long_labels[cluster] = long_variable_names
        for name, state in zip(long_variable_names, states[long_indices]):
            long_table.append([name, state])

    # Convert the long_table to a DataFrame and print it
    long_table_df = pd.DataFrame(long_table, columns=['Variable Name', 'State'])

    # Add 'Price' column to the long_table DataFrame
    long_table_df['Price'] = long_table_df['Variable Name'].apply(lambda name: closing_table[variable_names.tolist().index(name), -1])

    # Add 'Volume' column to the long_table DataFrame using the mean of the last 10 values in volume_data
    long_table_df['Volume'] = long_table_df['Variable Name'].apply(lambda name: np.mean(volume_table[variable_names.tolist().index(name), -10:]))

    # Find variables whose state is greater than 3.4 and give them a label of Short
    short_labels = {}
    short_table = []

    for cluster, states in cluster_current_state.items():
        short_indices = np.where(states > 3.4)[0]
        cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
        short_variable_names = variable_names[cluster_indices][short_indices]
        short_labels[cluster] = short_variable_names
        for name, state in zip(short_variable_names, states[short_indices]):
            short_table.append([name, state])

    # Convert the short_table to a DataFrame and print it
    short_table_df = pd.DataFrame(short_table, columns=['Variable Name', 'State'])

    # Add 'Price' column to the short_table DataFrame
    short_table_df['Price'] = short_table_df['Variable Name'].apply(lambda name: closing_table[variable_names.tolist().index(name), -1])

    # Add 'Volume' column to the short_table DataFrame using the mean of the last 10 values in volume_data
    short_table_df['Volume'] = short_table_df['Variable Name'].apply(lambda name: np.mean(volume_table[variable_names.tolist().index(name), -10:]))

    # Combine long_table_df and short_table_df into a single DataFrame
    combined_table_df = pd.concat([long_table_df, short_table_df], ignore_index=True)

    # Add 'Type' column to the combined_table_df
    combined_table_df['Type'] = combined_table_df['State'].apply(lambda state: 'Long' if state < 0 else 'Short')

    # Keep rows in combined_table_df with Price > 0 and Volume > 10000
    filtered_combined_table_df = combined_table_df[(combined_table_df['Price'] > 0) & (combined_table_df['Volume'] > 100000)]

    # Find values for end_timepoint+1:end_timepoint+21 for all variable names in filtered_combined_table_df
    future_timepoints = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[end_timepoint+1:end_timepoint+21]

    # Filter future_timepoints to include only the variable names in filtered_combined_table_df
    future_values = future_timepoints[filtered_combined_table_df['Variable Name'].values]

    # Calculate future values for long variables
    future_values_diff = future_values.iloc[1:].values - future_values.iloc[0].values

    # Convert future_values_diff to a DataFrame with variable names from future_values
    future_values_diff_df = pd.DataFrame(future_values_diff, columns=future_values.columns)

    # Initialize the RPS column
    filtered_combined_table_df['RPS'] = np.nan

    # Assess the number of positive values for 'Long' type variables
    for index, row in filtered_combined_table_df[filtered_combined_table_df['Type'] == 'Long'].iterrows():
        variable_name = row['Variable Name']
        positive_values = future_values_diff_df[variable_name][future_values_diff_df[variable_name] > 0]
        
        if len(positive_values) >= 5:
            filtered_combined_table_df.at[index, 'RPS'] = positive_values.iloc[4]
        else:
            filtered_combined_table_df.at[index, 'RPS'] = future_values_diff_df[variable_name].iloc[-1]

    # Assess the number of negative values for 'Short' type variables
    for index, row in filtered_combined_table_df[filtered_combined_table_df['Type'] == 'Short'].iterrows():
        variable_name = row['Variable Name']
        negative_values = future_values_diff_df[variable_name][future_values_diff_df[variable_name] < 0]
        
        if len(negative_values) >= 5:
            filtered_combined_table_df.at[index, 'RPS'] = negative_values.iloc[4]
        else:
            filtered_combined_table_df.at[index, 'RPS'] = future_values_diff_df[variable_name].iloc[-1]

    # Add 'End Timepoint' column to the filtered_combined_table_df
    filtered_combined_table_df['End Timepoint'] = end_timepoint

    # Append the filtered_combined_table_df to the all_filtered_combined_table_df
    all_filtered_combined_table_df = pd.concat([all_filtered_combined_table_df, filtered_combined_table_df], ignore_index=True)

