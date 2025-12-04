-- MySQL DDL: Core structured schema for Book Recommendation System

CREATE DATABASE IF NOT EXISTS bookrec;
USE bookrec;

-- Drop tables if exist (for clean setup)
DROP TABLE IF EXISTS ratings;
DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS book_root_genres;
DROP TABLE IF EXISTS book_subgenres;
DROP TABLE IF EXISTS root_genres;
DROP TABLE IF EXISTS subgenres;

-- Users table: core user identity and demographics
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    age TINYINT UNSIGNED NOT NULL,
    age_group VARCHAR(20) NOT NULL, -- added based on age("child_ls_12", "juvenile_12_17", "young_adult_18_24", "adult_25_34", "adult_35_49","adult_50_60", "senior_gt_60",)
    gender VARCHAR(10) NOT NULL,    -- artificially added at random ['Male','Female', 'Other']    location VARCHAR(200), -- free-form location like "renton, washington, usa"
    country CHAR(50) NOT NULL,   
    loc_latitude DECIMAL(9,6) NOT NULL,    -- more precise & stable than FLOAT
    loc_longitude DECIMAL(9,6) NOT NULL,   -- geographic data derived from geopy
    -- addition of some flags, we might remove if it doesn't improve the queries' preformances
    has_ratings BOOLEAN DEFAULT FALSE,
    has_preferences BOOLEAN NOT NULL, -- we might create a user with or without preferences
    -- INDEX idx_user(user_id)
    -- INDEX idx_users_country(country_iso2)
    -- INDEX idx_location (loc_latitude, loc_longitude) -- spatial index
);

-- Books table: core book metadata (reference data)
-- Goal is to avoid having sparce tables, so columns with a lot of missing data
--     should be moved to MongoDB to make use of document structure flexibility
CREATE TABLE books (
    isbn VARCHAR(10) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    authors TEXT,             -- array-like string; use TEXT for variable length
    publication_year SMALLINT UNSIGNED,
    publisher VARCHAR(150),
    -- price_usd DECIMAL(7,2),   --  Most might be synthetic, because most are NaN we decided to move to MongoDB
    genre VARCHAR(100)           -- Most might be uncategorized
    -- INDEX idx_books_title(title(255)),
    -- INDEX idx_books_pubyear(publication_year)
);


-- Ratings table: rating events
CREATE TABLE ratings (
    user_id INT,
    isbn VARCHAR(10) NOT NULL,
    rating TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (user_id, isbn),
    ratings_seq INT AUTO_INCREMENT UNIQUE,
    r_seq_user INT NOT NULL,
    r_seq_book INT NOT NULL,
    r_cat VARCHAR(50) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE,
    CHECK (rating BETWEEN 0 AND 10)
    -- INDEX idx_ratings_user(user_id),
    -- INDEX idx_ratings_isbn(isbn),
);


-- Trigger to auto-increment r_seq_user and r_seq_book on INSERT
-- Only kicks in if values are NULL (allows manual setting during bulk load)
DELIMITER $$

CREATE TRIGGER before_ratings_insert
BEFORE INSERT ON ratings
FOR EACH ROW
BEGIN
    -- Auto-increment r_seq_user for this user_id (only if NULL)
    IF NEW.r_seq_user IS NULL THEN
        SET NEW.r_seq_user = IFNULL(
            (SELECT MAX(r_seq_user) + 1 FROM ratings WHERE user_id = NEW.user_id),
            1
        );
    END IF;
    
    -- Auto-increment r_seq_book for this isbn (only if NULL)
    IF NEW.r_seq_book IS NULL THEN
        SET NEW.r_seq_book = IFNULL(
            (SELECT MAX(r_seq_book) + 1 FROM ratings WHERE isbn = NEW.isbn),
            1
        );
    END IF;
END$$

DELIMITER ;

-- Junction tables (many-to-many relationships)
CREATE TABLE book_root_genres (
    isbn VARCHAR(10),
    root_id INT,
    PRIMARY KEY (isbn, root_id),
    FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE,
    FOREIGN KEY (root_id) REFERENCES root_genres(root_id) ON DELETE CASCADE
    --INDEX idx_root_lookup (root_id, isbn)
    --INDEX idx_book_root_rootid(root_id)?
);

CREATE TABLE book_subgenres (
    isbn VARCHAR(10),
    subgenre_id INT,
    PRIMARY KEY (isbn, subgenre_id),
    FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE,
    FOREIGN KEY (subgenre_id) REFERENCES subgenres(subgenre_id) ON DELETE CASCADE
    --INDEX idx_subcat_lookup (subgenre_id, isbn)
    --INDEX idx_book_sub_subid(subgenre_id)?
);

CREATE TABLE root_genres (
    root_id INT AUTO_INCREMENT PRIMARY KEY,
    root_name VARCHAR(100) UNIQUE NOT NULL
);

-- Fixed subgenres table (no self-referencing FK)
CREATE TABLE subgenres (
    subgenre_id INT AUTO_INCREMENT PRIMARY KEY,
    subgenre_name VARCHAR(100) UNIQUE NOT NULL,
    root_id INT, -- included for hierarchical search
    FOREIGN KEY (root_id) REFERENCES root_genres(root_id) ON DELETE CASCADESET NULL
    --INDEX idx_subgenres_root(root_id)
);
