#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <dlib/dnn.h>
#include <dlib/matrix.h>

#include <string>
#include <stdexcept>

//---------------------------------------------------------------------------
// 1) Re‑declare your net_type exactly as in your training code:
using net_type = dlib::loss_multiclass_log<
                    dlib::fc<10,
                      dlib::relu<dlib::fc<84,
                        dlib::relu<dlib::fc<120,
                          dlib::relu<dlib::con<16,2,2,1,1,
                            dlib::relu<dlib::con<6,2,2,1,1,
                              dlib::input<dlib::matrix<double>>
                            >>
                          >>
                        >>
                      >>
                    >
                  >;

//---------------------------------------------------------------------------
// 2) A single global pointer:
static net_type* g_net = nullptr;

//---------------------------------------------------------------------------
// 3) Load the model from disk
void load_model(const std::string& path) {
    if (g_net) {
        delete g_net;
        g_net = nullptr;
    }
    g_net = new net_type();
    dlib::deserialize(path) >> *g_net;
}

//---------------------------------------------------------------------------
// 4) Turn a flat std::vector<double> into a matrix and predict:
unsigned long predict(const std::vector<double>& flat,
                      unsigned long rows,
                      unsigned long cols) {
    if (!g_net) {
        throw std::runtime_error("Model not loaded; call load_model() first");
    }
    if (flat.size() != rows * cols) {
        throw std::runtime_error("Input size mismatch");
    }

    // build a dlib::matrix from the flat vector
    dlib::matrix<double> m(rows, cols);
    for (size_t i = 0; i < flat.size(); ++i)
        m(i / cols, i % cols) = flat[i];

    // run the network
    return (*g_net)(m);
}

//---------------------------------------------------------------------------
// 5) Expose to Python
namespace py = pybind11;
PYBIND11_MODULE(dnn_wrapper, m) {
    m.doc() = "DNN inference via Pybind11";

    m.def("load_model", &load_model,
          "Loads a DNN from the given file path");
    m.def("predict", &predict,
          "Predict a label from a flat sample: (flat_vector, rows, cols)");
}
