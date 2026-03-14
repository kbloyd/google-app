def pretty_print_table(data):
    if not data:
        return "Table is empty."

    # 1. Find the maximum width for each column
    # This looks at every row for each column index and finds the longest string
    num_columns = len(data[0])
    col_widths = []
    for i in range(num_columns):
        max_width = max(len(str(row[i])) for row in data)
        col_widths.append(max_width)

    # 2. Create a format string (e.g., "{:<10} | {:<15}")
    # The '<' ensures left alignment
    format_str = " | ".join([f"{{:<{w}}}" for w in col_widths])

    # 3. Build the table
    output = []
    for i, row in enumerate(data):
        output.append(format_str.format(*row))
        
        # Add a separator line after the header (first row)
        if i == 0:
            output.append("-" * (sum(col_widths) + (3 * (num_columns - 1))))

    return "\n".join(output)

# Example Usage:
table_data = [
    ["Name", "Occupation", "Location"], # Header
    ["Alice", "Software Engineer", "New York"],
    ["Bob", "Artist", "San Francisco"],
    ["Charlie", "Chef", "Paris"]
]

print(pretty_print_table(table_data))