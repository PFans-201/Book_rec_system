-- MySQL DDL: Core structured schema for Book Recommendation System

CREATE DATABASE IF NOT EXISTS bookrec;
USE bookrec;

-- Drop tables if exist (for clean setup)
-- Must drop in reverse FK dependency order
DROP TABLE IF EXISTS ratings;
DROP TABLE IF EXISTS book_root_genres;
DROP TABLE IF EXISTS book_subgenres;
DROP TABLE IF EXISTS subgenres;
DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS root_genres;

-- Users table: core user identity and demographics
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    age TINYINT UNSIGNED NOT NULL,
    age_group VARCHAR(20) NOT NULL, -- age groups like "young_adult_18_24", etc.
    gender VARCHAR(10) NOT NULL,    -- ['Male','Female','Other']
    location VARCHAR(200),          -- free-form location like "renton, washington, usa"
    country CHAR(50) NOT NULL,
    loc_latitude DECIMAL(9,6),      -- Allow NULL for missing geocoding, Although it shouldn't happen
    loc_longitude DECIMAL(9,6),     -- Allow NULL for missing geocoding
    -- addition of some flags, we might remove if they don't improve performance
    has_ratings BOOLEAN DEFAULT FALSE,
    has_preferences BOOLEAN NOT NULL -- we might create a user with or without preferences
) ENGINE=InnoDB;

-- Books table: core book metadata (reference data)
-- Goal is to avoid having sparce tables, so columns with a lot of missing data
--     should be moved to MongoDB to make use of document structure flexibility
CREATE TABLE books (
    isbn VARCHAR(10) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    authors TEXT NOT NULL,             -- array-like string; use TEXT for variable length
    publication_year SMALLINT UNSIGNED NOT NULL,
    publisher VARCHAR(150) NOT NULL,
    -- price_usd DECIMAL(7,2),   -- moved to MongoDB due to sparsity
    genre VARCHAR(100)           -- may be uncategorized
) ENGINE=InnoDB;


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
) ENGINE=InnoDB;


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
-- Create referenced tables first
CREATE TABLE root_genres (
    root_id INT AUTO_INCREMENT PRIMARY KEY,
    root_name VARCHAR(100) UNIQUE NOT NULL
) ENGINE=InnoDB;

-- Fixed subgenres table (no self-referencing FK)
CREATE TABLE subgenres (
    subgenre_id INT AUTO_INCREMENT PRIMARY KEY,
    subgenre_name VARCHAR(100) UNIQUE NOT NULL,
    root_id INT, -- included for hierarchical search
    FOREIGN KEY (root_id) REFERENCES root_genres(root_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Then create junction tables that reference the above
CREATE TABLE book_root_genres (
    isbn VARCHAR(10),
    root_id INT,
    PRIMARY KEY (isbn, root_id),
    FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE,
    FOREIGN KEY (root_id) REFERENCES root_genres(root_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE book_subgenres (
    isbn VARCHAR(10),
    subgenre_id INT,
    PRIMARY KEY (isbn, subgenre_id),
    FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE,
    FOREIGN KEY (subgenre_id) REFERENCES subgenres(subgenre_id) ON DELETE CASCADE
) ENGINE=InnoDB;
