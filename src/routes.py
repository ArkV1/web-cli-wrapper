from flask import render_template, send_from_directory
import os

def register_routes(app):
    @app.route('/')
    def home():
        return render_template('base.html')

    @app.route('/website-to-pdf')
    def website_to_pdf():
        return render_template('website-to-pdf.html')

    @app.route('/website-to-source')
    def website_to_source():
        return render_template('website-to-source.html')