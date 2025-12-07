# top N most rated books

simple_mysql =  {
    "MySQL" :
        """
            SELECT book FROM books
            Where %s == cond 
        """
}

query_content_based = {
    "MySQL":
        """
            SELECT *
            ....
        """,
    "MongoDB":
        """
            
        """
}

