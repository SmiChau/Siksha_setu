from xhtml2pdf import pisa             # import python module

# Define your data
source_html = "doc_template.html"
output_filename = "SikshaSetu_Algorithm_Documentation.pdf"

# Utility function
def convert_html_to_pdf(source_html, output_filename):
    # open output file for writing (binary)
    result_file = open(output_filename, "w+b")

    # convert HTML to PDF
    pisa_status = pisa.CreatePDF(
            open(source_html, "r").read(),            # the HTML to convert
            dest=result_file)                          # file handle to recieve result

    # close output file
    result_file.close()                 # close output file

    # return True on success and False on errors
    return pisa_status.err

if __name__ == "__main__":
    pisa.showLogging()
    err = convert_html_to_pdf(source_html, output_filename)
    if not err:
        print(f"Successfully generated {output_filename}")
    else:
        print(f"Error occurred during conversion: {err}")
